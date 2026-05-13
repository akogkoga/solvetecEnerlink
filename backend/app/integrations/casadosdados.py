"""Adaptador para Casa dos Dados v5 — busca de empresas por filtros."""
import re
import asyncio
import logging
import time
from typing import List, Optional
from app.integrations.base import BaseAPIAdapter
from app.models.schemas import FilterRequest, LeadNormalized
from app.core.config import CASADOSDADOS_URL, CASADOSDADOS_API_KEY
from app.services.health_tracker import health_tracker

logger = logging.getLogger(__name__)


class CasaDosDadosAdapter(BaseAPIAdapter):
    """
    Casa dos Dados v5 — Provider PRINCIPAL de busca por filtros.
    Endpoint: POST https://api.casadosdados.com.br/v5/cnpj/pesquisa
    Requer API key (cadastro em portal.casadosdados.com.br).
    Sem API key: retorna 401 e fallback para providers alternativos.
    """

    PROVIDER_NAME = "CasaDosDados"
    RATE_DELAY = 2.0
    MAX_PAGES = 5

    async def fetch_leads(self, filters: FilterRequest) -> List[dict]:
        """Busca empresas reais usando filtros via Casa dos Dados v5."""
        if not CASADOSDADOS_API_KEY:
            self.logger.warning(
                "API key não configurada (CASADOSDADOS_API_KEY). "
                "Cadastre-se em portal.casadosdados.com.br"
            )
            return []

        all_results: List[dict] = []
        target_count = filters.quantidade or 100
        page = 1

        while len(all_results) < target_count and page <= self.MAX_PAGES:
            payload = self._build_payload(filters, page)
            self.logger.info(
                "Buscando página %d — CNAE=%s UF=%s Cidade=%s",
                page, filters.cnae, filters.estado, filters.cidade,
            )

            data = await self._fetch_page(payload)
            if data is None:
                break

            companies = self._extract_companies(data)
            if not companies:
                self.logger.info("Sem mais resultados na página %d", page)
                break

            all_results.extend(companies)
            self.logger.info(
                "Página %d: %d empresas (total: %d)",
                page, len(companies), len(all_results),
            )
            page += 1

        return all_results[:target_count]

    async def _fetch_page(self, payload: dict) -> Optional[dict]:
        """Busca página via cloudscraper ou httpx com autenticação."""
        headers = self._build_headers()

        # Tenta cloudscraper primeiro (bypass Cloudflare)
        result = await self._fetch_with_cloudscraper(payload, headers)
        if result is not None:
            return result

        self.logger.info("Cloudscraper indisponível, tentando httpx")
        return await self._fetch_with_httpx(payload, headers)

    def _build_headers(self) -> dict:
        """Constrói headers com autenticação Bearer."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {CASADOSDADOS_API_KEY}",
        }

    async def _fetch_with_cloudscraper(
        self, payload: dict, headers: dict,
    ) -> Optional[dict]:
        """Usa cloudscraper em thread separada para bypass Cloudflare."""
        try:
            import cloudscraper
        except ImportError:
            return None

        start = time.monotonic()
        try:
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows"},
            )
            response = await asyncio.to_thread(
                scraper.post, CASADOSDADOS_URL,
                json=payload, headers=headers, timeout=15,
            )
            elapsed_ms = (time.monotonic() - start) * 1000

            if response.status_code == 401:
                self.logger.error("API key inválida ou expirada (401)")
                health_tracker.record_failure(self.PROVIDER_NAME, "401 Unauthorized")
                return None

            if response.status_code != 200:
                self.logger.error(
                    "Cloudscraper status %d", response.status_code,
                )
                health_tracker.record_failure(
                    self.PROVIDER_NAME, f"status {response.status_code}",
                )
                return None

            health_tracker.record_success(self.PROVIDER_NAME, elapsed_ms)
            return response.json()

        except Exception as exc:
            health_tracker.record_failure(self.PROVIDER_NAME, str(exc))
            self.logger.error("Cloudscraper erro: %s", str(exc))
            return None

    async def _fetch_with_httpx(
        self, payload: dict, headers: dict,
    ) -> Optional[dict]:
        """Fallback via httpx com headers de autenticação."""
        response = await self._request_with_retry(
            "POST", CASADOSDADOS_URL,
            json=payload, headers=headers,
        )
        if response is None:
            return None

        if response.status_code == 401:
            self.logger.error("API key inválida ou expirada (401)")
            return None

        if response.status_code != 200:
            self.logger.error(
                "httpx status %d (provável Cloudflare)",
                response.status_code,
            )
            return None

        return response.json()

    def _build_payload(self, filters: FilterRequest, page: int) -> dict:
        """Monta o payload de busca da Casa dos Dados v5."""
        atividade_principal = [filters.cnae] if filters.cnae else []
        uf = [filters.estado.upper()] if filters.estado else []
        municipio = [filters.cidade.upper()] if filters.cidade else []

        return {
            "query": {
                "termo": [filters.termo] if filters.termo else [],
                "atividade_principal": atividade_principal,
                "natureza_juridica": [],
                "uf": uf,
                "municipio": municipio,
                "situacao_cadastral": "ATIVA",
                "cep": [],
                "ddd": [],
            },
            "range_query": {
                "data_abertura": {"lte": None, "gte": None},
                "capital_social": {"lte": None, "gte": None},
            },
            "extras": {
                "somente_mei": False,
                "excluir_mei": False,
                "com_email": False,
                "incluir_atividade_secundaria": False,
                "com_contato_telefonico": False,
                "somente_celular": False,
                "somente_fixo": False,
                "somente_matriz": False,
                "somente_filial": False,
            },
            "page": page,
        }

    def _extract_companies(self, data: dict) -> List[dict]:
        """Extrai lista de empresas da resposta da API."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("cnpj", "data", "results", "empresas", "items"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []

    def normalize(self, raw_data: dict) -> LeadNormalized:
        """Converte resposta da Casa dos Dados para formato padrão."""
        cnpj_clean = re.sub(r"\D", "", raw_data.get("cnpj", "") or "")

        telefone = (
            raw_data.get("telefone", "")
            or raw_data.get("ddd_telefone_1", "")
            or ""
        )
        telefone = re.sub(r"\D", "", telefone)

        email = (
            raw_data.get("email", "")
            or raw_data.get("correio_eletronico", "")
            or ""
        )
        cidade = raw_data.get("municipio", "") or raw_data.get("cidade", "") or ""
        porte = raw_data.get("porte", "") or raw_data.get("porte_empresa", "") or ""
        cnae_desc = self._extract_cnae(raw_data)
        situacao = (
            raw_data.get("situacao_cadastral", "")
            or raw_data.get("descricao_situacao_cadastral", "")
            or "ATIVA"
        )
        empresa = (
            raw_data.get("razao_social", "")
            or raw_data.get("nome_fantasia", "")
            or ""
        )

        return LeadNormalized(
            empresa=empresa,
            cnpj=cnpj_clean,
            telefone=telefone,
            email=email.lower() if email else "",
            cidade=cidade,
            estado=raw_data.get("uf", "") or "",
            cnae=cnae_desc,
            porte=porte,
            site="",
            situacao=situacao,
            fonte="CasaDosDados",
        )

    @staticmethod
    def _extract_cnae(raw_data: dict) -> str:
        """Extrai descrição do CNAE de diferentes formatos."""
        cnae_desc = (
            raw_data.get("cnae_fiscal_descricao", "")
            or raw_data.get("atividade_principal", "")
            or ""
        )
        if isinstance(cnae_desc, list) and cnae_desc:
            first = cnae_desc[0]
            return first.get("text", "") if isinstance(first, dict) else str(first)
        return cnae_desc if isinstance(cnae_desc, str) else ""
