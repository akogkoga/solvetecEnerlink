"""Provider manager with deterministic discovery fallback and enrichment."""
import asyncio
import logging
import time
from typing import List, Optional, Tuple

from app.core.config import ENRICHMENT_MODE, MAX_ENRICHMENT_CONCURRENT, MAX_ENRICHMENT_LEADS
from app.integrations.brasilapi import BrasilAPIAdapter
from app.integrations.casadosdados import CasaDosDadosAdapter
from app.integrations.cnpja import CNPJaAdapter
from app.integrations.cnpjws import CNPJWSAdapter
from app.integrations.receitaws import ReceitaWSAdapter
from app.integrations.seed_provider import SeedDatasetProvider
from app.integrations.sqlite_provider import SQLiteDiscoveryProvider
from app.models.schemas import FilterRequest, LeadNormalized
from app.services.provider_registry import ProviderInfo, ProviderRegistry, ProviderType

logger = logging.getLogger("service.provider_manager")


def _build_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(ProviderInfo(
        name="SQLiteLocal",
        provider_type=ProviderType.DISCOVERY,
        priority=0,
        adapter=SQLiteDiscoveryProvider(),
        description="Receita Federal local (SQLite)",
    ))
    registry.register(ProviderInfo(
        name="SeedDataset",
        provider_type=ProviderType.DISCOVERY,
        priority=1,
        adapter=SeedDatasetProvider(),
        description="Curated/local dataset of real CNPJs",
    ))
    registry.register(ProviderInfo(
        name="CasaDosDados",
        provider_type=ProviderType.DISCOVERY,
        priority=2,
        adapter=CasaDosDadosAdapter(),
        description="Casa dos Dados v5",
        requires_key=True,
    ))
    registry.register(ProviderInfo(
        name="BrasilAPI",
        provider_type=ProviderType.ENRICHMENT,
        priority=1,
        adapter=BrasilAPIAdapter(),
        description="BrasilAPI CNPJ enrichment",
    ))
    registry.register(ProviderInfo(
        name="CNPJWS",
        provider_type=ProviderType.ENRICHMENT,
        priority=2,
        adapter=CNPJWSAdapter(),
        description="CNPJ.ws public enrichment",
    ))
    registry.register(ProviderInfo(
        name="CNPJa",
        provider_type=ProviderType.ENRICHMENT,
        priority=3,
        adapter=CNPJaAdapter(),
        description="CNPJa Open enrichment",
    ))
    registry.register(ProviderInfo(
        name="ReceitaWS",
        provider_type=ProviderType.ENRICHMENT,
        priority=4,
        adapter=ReceitaWSAdapter(),
        description="ReceitaWS enrichment",
    ))
    return registry


class ProviderManager:
    """Coordinates discovery, normalization, enrichment and provider metadata."""

    def __init__(self):
        self.registry = _build_registry()
        self.providers_used: List[str] = []
        self.errors: List[str] = []

    async def search_leads(self, filters: FilterRequest) -> List[LeadNormalized]:
        self.providers_used = []
        self.errors = []

        normalized = await self._multi_discovery(filters)
        if not normalized:
            return []

        logger.info(
            "Discovery normalized %d leads via %s",
            len(normalized), ", ".join(self.providers_used) or "none",
        )
        return await self._enrich_incomplete(normalized, filters)

    async def _multi_discovery(self, filters: FilterRequest) -> List[LeadNormalized]:
        target = filters.quantidade or 100
        discovered: List[LeadNormalized] = []
        seen_cnpjs: set[str] = set()
        fallback_plan = self._build_fallback_plan(filters)

        for info in self.registry.get_discovery_providers():
            if not info.is_healthy:
                msg = f"{info.name}: unhealthy, skipped"
                self.errors.append(msg)
                logger.info(msg)
                continue

            for step_index, (step_label, step_filters) in enumerate(fallback_plan):
                if step_index:
                    logger.info(
                        "Discovery fallback step %d provider=%s: %s",
                        step_index, info.name, step_label,
                    )

                start = time.monotonic()
                logger.info(
                    "Discovery trying %s priority=%d step=%s",
                    info.name, info.priority, step_label,
                )
                try:
                    raw_results = await info.adapter.fetch_leads(step_filters)
                except Exception as exc:
                    msg = f"{info.name}: {exc}"
                    self.errors.append(msg)
                    logger.exception("Discovery failed: %s", msg)
                    continue

                elapsed_ms = int((time.monotonic() - start) * 1000)
                if not raw_results:
                    logger.info("%s: no results in %dms step=%s", info.name, elapsed_ms, step_label)
                    continue

                provider_leads = self._normalize_results(raw_results, info.name)
                added = 0
                for lead in provider_leads:
                    if lead.cnpj in seen_cnpjs:
                        continue
                    seen_cnpjs.add(lead.cnpj)
                    discovered.append(lead)
                    added += 1

                if added and info.name not in self.providers_used:
                    self.providers_used.append(info.name)

                logger.info(
                    "DISCOVERY OK %s raw=%d normalized=%d added=%d total=%d in %dms step=%s",
                    info.name, len(raw_results), len(provider_leads), added,
                    len(discovered), elapsed_ms, step_label,
                )

                if len(discovered) >= target:
                    break

            if discovered:
                if step_index:
                    self.errors.append(
                        f"Resultados ajustados para ampliar a busca: {step_label}"
                    )
                break

        if not discovered:
            self.errors.append("Nenhum resultado encontrado apos fallback progressivo")
            logger.warning("No discovery provider returned usable leads")
        return discovered

    @staticmethod
    def _build_fallback_plan(filters: FilterRequest) -> List[Tuple[str, FilterRequest]]:
        """Builds progressively broader discovery attempts without changing the API contract."""
        plan: List[Tuple[str, FilterRequest]] = [("filtros originais", filters)]

        if filters.cidade:
            plan.append((
                "cidade removida; busca ampliada para o estado",
                filters.model_copy(update={"cidade": None}),
            ))

        if filters.termo:
            plan.append((
                "termo exato flexibilizado; mantendo regiao e demais filtros",
                filters.model_copy(update={"termo": None, "nome": None}),
            ))

        if filters.cnae:
            plan.append((
                "CNAE removido; busca por segmento aproximado",
                filters.model_copy(update={"cnae": None}),
            ))

        if filters.estado:
            plan.append((
                "apenas estado mantido",
                filters.model_copy(update={
                    "cidade": None,
                    "termo": None,
                    "nome": None,
                    "cnae": None,
                    "porte": None,
                    "natureza_juridica": None,
                    "mei": None,
                }),
            ))

        plan.append((
            "busca geral sem filtros restritivos",
            filters.model_copy(update={
                "cidade": None,
                "estado": None,
                "termo": None,
                "nome": None,
                "cnae": None,
                "porte": None,
                "natureza_juridica": None,
                "mei": None,
            }),
        ))

        deduped: List[Tuple[str, FilterRequest]] = []
        seen_keys: set[str] = set()
        for label, candidate in plan:
            key = candidate.model_dump_json()
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append((label, candidate))
        return deduped

    def _normalize_results(self, raw_results: List[dict], provider_name: Optional[str]) -> List[LeadNormalized]:
        adapter = self._find_adapter(provider_name)
        if adapter is None:
            return []

        normalized: List[LeadNormalized] = []
        for raw in raw_results:
            try:
                lead = adapter.normalize(raw)
                lead.cnpj = "".join(ch for ch in lead.cnpj if ch.isdigit())
                if not lead.empresa or len(lead.cnpj) != 14:
                    continue
                normalized.append(lead)
            except Exception as exc:
                logger.warning("Normalize error from %s: %s", provider_name, exc)
        return normalized

    def _find_adapter(self, name: Optional[str]) -> Optional[object]:
        if name is None:
            return None
        for info in self.registry.get_all():
            if info.name == name:
                return info.adapter
        return None

    async def _enrich_incomplete(self, leads: List[LeadNormalized], filters: FilterRequest) -> List[LeadNormalized]:
        incomplete = [lead for lead in leads if self._is_incomplete(lead)]
        if not incomplete:
            return leads

        limit = min(len(incomplete), MAX_ENRICHMENT_LEADS, filters.quantidade or MAX_ENRICHMENT_LEADS)
        selected = incomplete[:limit]
        skipped = len(incomplete) - len(selected)
        if skipped:
            self.errors.append(f"Enrichment limited to {limit} leads; {skipped} queued for future pages")

        logger.info("Enriching %d/%d incomplete leads", len(selected), len(leads))
        enriched_map = await self._enrich_batch(selected)
        if not enriched_map:
            return leads

        result: List[LeadNormalized] = []
        for lead in leads:
            enriched = enriched_map.get(lead.cnpj)
            result.append(self._merge_lead_data(lead, enriched) if enriched else lead)
        return result

    @staticmethod
    def _is_incomplete(lead: LeadNormalized) -> bool:
        phone_digits = "".join(ch for ch in (lead.telefone or "") if ch.isdigit())
        has_masked_phone = "*" in (lead.telefone or "") and len(phone_digits) >= 4
        no_phone = not phone_digits or (len(phone_digits) < 8 and not has_masked_phone)
        has_email = "@" in (lead.email or "") or "*" in (lead.email or "")
        no_email = not has_email
        missing_core = not lead.cidade or not lead.estado or not lead.cnae
        if ENRICHMENT_MODE == "aggressive":
            return no_phone or no_email or missing_core
        return (no_phone and no_email) or missing_core

    async def enrich_lead(self, cnpj: str) -> Optional[LeadNormalized]:
        for info in self.registry.get_enrichment_providers():
            if not info.is_healthy:
                logger.info("Skipping enrichment %s because it is unhealthy", info.name)
                continue
            try:
                raw = await info.adapter.fetch_by_cnpj(cnpj)
                if raw:
                    lead = info.adapter.normalize(raw)
                    if lead and info.name not in self.providers_used:
                        self.providers_used.append(info.name)
                    return lead
            except Exception as exc:
                msg = f"{info.name}: {cnpj} enrichment failed: {exc}"
                self.errors.append(msg)
                logger.warning(msg)
        return None

    async def _enrich_batch(self, leads: List[LeadNormalized]) -> dict[str, LeadNormalized]:
        semaphore = asyncio.Semaphore(MAX_ENRICHMENT_CONCURRENT)
        results: dict[str, LeadNormalized] = {}

        async def _enrich_one(lead: LeadNormalized) -> None:
            async with semaphore:
                enriched = await self.enrich_lead(lead.cnpj)
                if enriched:
                    results[lead.cnpj] = enriched

        await asyncio.gather(*[_enrich_one(lead) for lead in leads], return_exceptions=True)
        return results

    @staticmethod
    def _merge_lead_data(original: LeadNormalized, enriched: LeadNormalized) -> LeadNormalized:
        return LeadNormalized(
            empresa=original.empresa or enriched.empresa,
            cnpj=original.cnpj,
            telefone=original.telefone or enriched.telefone,
            email=original.email or enriched.email,
            cidade=original.cidade or enriched.cidade,
            estado=original.estado or enriched.estado,
            cnae=original.cnae or enriched.cnae,
            porte=original.porte or enriched.porte,
            site=original.site or enriched.site,
            situacao=original.situacao or enriched.situacao,
            fonte=f"{original.fonte}+{enriched.fonte}",
        )

    def get_status(self) -> dict:
        return {
            "providers": self.registry.get_status(),
            "discovery_count": len(self.registry.get_discovery_providers()),
            "enrichment_count": len(self.registry.get_enrichment_providers()),
        }
