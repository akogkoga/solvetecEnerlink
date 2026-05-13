"""Local seed discovery provider."""
import json
import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import List

from app.integrations.base import BaseAPIAdapter
from app.models.schemas import FilterRequest, LeadNormalized
from app.services.health_tracker import health_tracker

logger = logging.getLogger("provider.SeedDataset")

SEED_FILE = Path(__file__).parent.parent.parent / "data" / "seed_cnpjs.json"


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.upper().strip()


class SeedDatasetProvider(BaseAPIAdapter):
    """Discovery over a curated/local JSON dataset."""

    PROVIDER_NAME = "SeedDataset"
    RATE_DELAY = 0

    def __init__(self):
        super().__init__()
        self._data: List[dict] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not SEED_FILE.exists():
            self.logger.warning("Seed file not found: %s", SEED_FILE)
            health_tracker.record_failure(self.PROVIDER_NAME, "seed file not found")
            return
        try:
            raw = json.loads(SEED_FILE.read_text(encoding="utf-8-sig"))
            companies = raw.get("companies", []) if isinstance(raw, dict) else raw
            self._data = [c for c in companies if isinstance(c, dict) and _digits(c.get("cnpj"))]
            self.logger.info("Seed loaded: %d companies", len(self._data))
        except Exception as exc:
            self.logger.error("Seed load error: %s", exc)
            health_tracker.record_failure(self.PROVIDER_NAME, str(exc))

    async def fetch_leads(self, filters: FilterRequest) -> List[dict]:
        start = time.monotonic()
        self._ensure_loaded()
        if not self._data:
            return []

        target = filters.quantidade or 100
        offset = ((filters.pagina or 1) - 1) * target
        candidates = self._ranked_matches(filters)
        page = candidates[offset:offset + target]
        elapsed_ms = (time.monotonic() - start) * 1000
        health_tracker.record_success(self.PROVIDER_NAME, elapsed_ms)
        self.logger.info("Seed returned %d/%d leads in %.0fms", len(page), len(candidates), elapsed_ms)
        return page

    def _ranked_matches(self, filters: FilterRequest) -> List[dict]:
        strict: list[tuple[int, dict]] = []
        relaxed: list[tuple[int, dict]] = []

        for company in self._data:
            location_ok = self._match_location(company, filters)
            cnae_ok = self._match_cnae(company, filters)
            porte_ok = self._match_porte(company, filters)
            term_ok = self._match_term(company, filters)

            if location_ok and cnae_ok and porte_ok and term_ok:
                strict.append((self._quality_rank(company), company))
            elif location_ok and porte_ok and term_ok and not filters.cnae:
                relaxed.append((self._quality_rank(company), company))
            elif location_ok and porte_ok and not strict:
                relaxed.append((self._quality_rank(company) - 20, company))

        matches = strict if strict else relaxed
        if not matches and filters.estado:
            matches = [
                (self._quality_rank(c) - 40, c)
                for c in self._data
                if _norm(c.get("uf")) == filters.estado.upper()
            ]
        if not matches and not any([filters.estado, filters.cidade, filters.cnae, filters.porte, filters.termo]):
            matches = [(self._quality_rank(c), c) for c in self._data]

        matches.sort(key=lambda item: item[0], reverse=True)
        return [company for _, company in matches]

    @staticmethod
    def _match_location(company: dict, filters: FilterRequest) -> bool:
        if filters.estado and _norm(company.get("uf")) != filters.estado.upper():
            return False
        if filters.cidade:
            city = _norm(filters.cidade)
            company_city = _norm(company.get("municipio") or company.get("cidade"))
            if city not in company_city and company_city not in city:
                return False
        return True

    @staticmethod
    def _match_cnae(company: dict, filters: FilterRequest) -> bool:
        if not filters.cnae:
            return True
        code = _digits(company.get("cnae_fiscal"))
        wanted = filters.cnae
        wanted_prefix = wanted[:-2] if wanted.endswith("00") and len(wanted) >= 4 else wanted
        desc = _norm(company.get("cnae_fiscal_descricao") or company.get("cnae"))
        secondary = " ".join(
            f"{_digits(item.get('codigo'))} {_norm(item.get('descricao'))}"
            for item in company.get("cnaes_secundarios", []) or []
            if isinstance(item, dict)
        )
        return wanted in code or code.startswith(wanted_prefix) or wanted in secondary or wanted_prefix in secondary or _norm(wanted) in desc

    @staticmethod
    def _match_term(company: dict, filters: FilterRequest) -> bool:
        if not filters.termo:
            return True
        term = _norm(filters.termo)
        aliases = {
            "TECNOLOGIA": ["TECNOLOGIA", "SOFTWARE", "INFORMATICA", "COMPUTADOR", "SISTEMAS"],
            "MARKETING": ["MARKETING", "PUBLICIDADE", "PROPAGANDA", "PROMOCAO", "AGENCIA"],
            "CONTABILIDADE": ["CONTABILIDADE", "CONTABIL", "AUDITORIA", "TRIBUTARIA"],
            "MEI": ["MEI", "MICROEMPREENDEDOR INDIVIDUAL", "EMPRESARIO INDIVIDUAL"],
            "LTDA": ["LTDA", "LIMITADA"],
        }
        needles = aliases.get(term, [term])
        searchable = " ".join([
            _norm(company.get("razao_social")),
            _norm(company.get("nome_fantasia")),
            _norm(company.get("cnae_fiscal_descricao")),
            _norm(company.get("porte")),
            _norm(company.get("natureza_juridica")),
            _norm(company.get("termos")),
            "MEI" if company.get("opcao_pelo_mei") else "",
        ])
        secondary = " ".join(
            _norm(item.get("descricao"))
            for item in company.get("cnaes_secundarios", []) or []
            if isinstance(item, dict)
        )
        searchable = f"{searchable} {secondary}"
        return any(needle in searchable for needle in needles)

    @staticmethod
    def _match_porte(company: dict, filters: FilterRequest) -> bool:
        if not filters.porte:
            return True
        return filters.porte.upper() in _norm(company.get("porte"))

    @staticmethod
    def _quality_rank(company: dict) -> int:
        return sum([
            40 if _digits(company.get("ddd_telefone_1") or company.get("telefone")) else 0,
            18 if "*" in str(company.get("telefone_publico") or "") else 0,
            30 if "@" in str(company.get("email") or company.get("email_publico") or "") else 0,
            10 if company.get("site") else 0,
            15 if _digits(company.get("cnae_fiscal")) else 0,
            10 if company.get("municipio") else 0,
            5 if company.get("porte") else 0,
        ])

    def normalize(self, raw_data: dict) -> LeadNormalized:
        raw_phone = raw_data.get("telefone") or raw_data.get("ddd_telefone_1") or raw_data.get("telefone_publico")
        telefone = str(raw_phone or "").strip() if "*" in str(raw_phone or "") else _digits(raw_phone)
        cnae = _digits(raw_data.get("cnae_fiscal")) or str(raw_data.get("cnae_fiscal_descricao") or raw_data.get("cnae") or "")
        situacao = raw_data.get("descricao_situacao_cadastral") or raw_data.get("situacao") or "ATIVA"
        raw_email = raw_data.get("email") or raw_data.get("email_publico") or ""

        return LeadNormalized(
            empresa=raw_data.get("razao_social", "") or raw_data.get("nome_fantasia", "") or "",
            cnpj=_digits(raw_data.get("cnpj")),
            telefone=telefone,
            email=str(raw_email or "").lower().strip(),
            cidade=raw_data.get("municipio", "") or raw_data.get("cidade", "") or "",
            estado=(raw_data.get("uf", "") or raw_data.get("estado", "") or "").upper(),
            cnae=cnae,
            porte=raw_data.get("porte", "") or "",
            site=raw_data.get("site", "") or "",
            situacao=str(situacao),
            fonte="SeedDataset",
        )

    @property
    def dataset_size(self) -> int:
        self._ensure_loaded()
        return len(self._data)
