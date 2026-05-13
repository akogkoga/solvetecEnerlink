"""Serviço principal de geração de leads — orquestra busca, deduplicação e scoring."""
import time
import logging
from typing import List
from app.models.schemas import FilterRequest, LeadResponse, LeadNormalized
from app.services.provider_manager import ProviderManager
from app.services.deduplicator import DeduplicatorService
from app.services.scorer import ScorerService
from app.services.cache import cache_instance, CacheService

logger = logging.getLogger("service.lead_generator")


class LeadGeneratorService:
    """Motor principal — coordena providers, deduplicação, score e cache."""

    def __init__(self):
        self.provider_manager = ProviderManager()
        self.cache = cache_instance

    async def generate(self, filters: FilterRequest) -> LeadResponse:
        """Gera leads reais com cache, deduplicação e scoring."""
        start_time = time.monotonic()

        cache_key = CacheService.make_key(filters.model_dump(mode="json"))
        cached = self.cache.get(cache_key)
        if cached:
            logger.info("Resposta servida do cache")
            return LeadResponse.model_validate(cached)

        normalized_leads = await self.provider_manager.search_leads(filters)

        if not normalized_leads:
            return self._build_empty_response(start_time)

        active_leads = self._filter_active(normalized_leads)
        unique_leads = DeduplicatorService.remove_duplicates(active_leads)

        if unique_leads:
            unique_leads = ScorerService.apply_scores(unique_leads)

        limit = filters.quantidade or 100
        final_leads = unique_leads[:limit]

        response = self._build_response(
            all_found=len(unique_leads),
            final_leads=final_leads,
            start_time=start_time,
        )

        self.cache.set(cache_key, response)
        return response

    @staticmethod
    def _filter_active(leads: List[LeadNormalized]) -> List[LeadNormalized]:
        """Filtra apenas empresas com situação ativa."""
        active = []
        for lead in leads:
            situacao = (lead.situacao or "").upper()
            is_active = (
                situacao in ("ATIVA", "02", "")
                or "ATIVA" in situacao
            )
            if is_active:
                active.append(lead)
        logger.info("Filtro ativas: %d → %d", len(leads), len(active))
        return active

    def _build_response(
        self,
        all_found: int,
        final_leads: List[LeadNormalized],
        start_time: float,
    ) -> LeadResponse:
        """Constrói resposta padronizada com metadados."""
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        return LeadResponse(
            total_found=all_found,
            total_returned=len(final_leads),
            leads=final_leads,
            providers_used=self.provider_manager.providers_used,
            search_time_ms=elapsed_ms,
            errors=self.provider_manager.errors,
        )

    def _build_empty_response(self, start_time: float) -> LeadResponse:
        """Constrói resposta vazia com metadados de erro."""
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        return LeadResponse(
            total_found=0,
            total_returned=0,
            leads=[],
            providers_used=self.provider_manager.providers_used,
            search_time_ms=elapsed_ms,
            errors=self.provider_manager.errors,
        )
