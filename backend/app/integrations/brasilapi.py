"""Adaptador real para BrasilAPI — consulta individual de CNPJ."""
import re
from typing import List, Optional
from app.integrations.base import BaseAPIAdapter
from app.models.schemas import FilterRequest, LeadNormalized
from app.core.config import BRASILAPI_URL, BRASILAPI_RATE_DELAY


class BrasilAPIAdapter(BaseAPIAdapter):
    """
    BrasilAPI — Provider de enriquecimento individual.
    Endpoint: GET https://brasilapi.com.br/api/cnpj/v1/{cnpj}
    Limitação: Apenas consulta por CNPJ individual (sem busca por filtros).
    Rate limit: Uso justo (sem limite rígido documentado).
    """

    PROVIDER_NAME = "BrasilAPI"
    RATE_DELAY = BRASILAPI_RATE_DELAY

    async def fetch_leads(self, filters: FilterRequest) -> List[dict]:
        """BrasilAPI não suporta busca por filtros — retorna lista vazia."""
        self.logger.info("BrasilAPI não suporta busca por filtros — ignorando")
        return []

    async def fetch_by_cnpj(self, cnpj: str) -> Optional[dict]:
        """Busca dados reais de uma empresa pelo CNPJ."""
        clean_cnpj = re.sub(r"\D", "", cnpj)
        url = f"{BRASILAPI_URL}/{clean_cnpj}"
        self.logger.info("Consultando CNPJ %s", clean_cnpj)

        response = await self._request_with_retry("GET", url)
        if response is None or response.status_code != 200:
            self.logger.warning("Falha ao consultar CNPJ %s", clean_cnpj)
            return None

        return response.json()

    def normalize(self, raw_data: dict) -> LeadNormalized:
        """Converte resposta da BrasilAPI para formato padrão."""
        telefone = raw_data.get("ddd_telefone_1", "") or ""
        telefone = re.sub(r"\D", "", telefone)

        return LeadNormalized(
            empresa=raw_data.get("razao_social", ""),
            cnpj=raw_data.get("cnpj", ""),
            telefone=telefone,
            email=raw_data.get("email", "") or "",
            cidade=raw_data.get("municipio", ""),
            estado=raw_data.get("uf", ""),
            cnae=raw_data.get("cnae_fiscal_descricao", ""),
            porte=raw_data.get("porte", ""),
            site="",
            situacao=raw_data.get("descricao_situacao_cadastral", ""),
            fonte="BrasilAPI",
        )
