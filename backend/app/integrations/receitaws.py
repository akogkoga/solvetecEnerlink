"""Adaptador real para ReceitaWS — consulta individual de CNPJ."""
import re
from typing import List, Optional
from app.integrations.base import BaseAPIAdapter
from app.models.schemas import FilterRequest, LeadNormalized
from app.core.config import RECEITAWS_URL, RECEITAWS_RATE_DELAY


class ReceitaWSAdapter(BaseAPIAdapter):
    """
    ReceitaWS — Provider de enriquecimento (fallback).
    Endpoint: GET https://receitaws.com.br/v1/cnpj/{cnpj}
    Rate limit: 3 req/min no plano gratuito (delay de 20s entre chamadas).
    """

    PROVIDER_NAME = "ReceitaWS"
    RATE_DELAY = RECEITAWS_RATE_DELAY

    async def fetch_leads(self, filters: FilterRequest) -> List[dict]:
        """ReceitaWS não suporta busca por filtros — retorna lista vazia."""
        self.logger.info("ReceitaWS não suporta busca por filtros — ignorando")
        return []

    async def fetch_by_cnpj(self, cnpj: str) -> Optional[dict]:
        """Busca dados reais de uma empresa pelo CNPJ."""
        clean_cnpj = re.sub(r"\D", "", cnpj)
        url = f"{RECEITAWS_URL}/{clean_cnpj}"
        self.logger.info("Consultando CNPJ %s", clean_cnpj)

        response = await self._request_with_retry("GET", url)
        if response is None or response.status_code != 200:
            return None

        data = response.json()
        if data.get("status") == "ERROR":
            self.logger.warning("ReceitaWS erro: %s", data.get("message", ""))
            return None

        return data

    def normalize(self, raw_data: dict) -> LeadNormalized:
        """Converte resposta da ReceitaWS para formato padrão."""
        telefone = raw_data.get("telefone", "") or ""
        telefone = re.sub(r"\D", "", telefone)

        email = raw_data.get("email", "") or ""
        cnpj = re.sub(r"\D", "", raw_data.get("cnpj", ""))

        atividades = raw_data.get("atividade_principal", [])
        cnae_desc = ""
        if atividades and isinstance(atividades, list):
            cnae_desc = atividades[0].get("text", "")

        return LeadNormalized(
            empresa=raw_data.get("nome", "") or raw_data.get("fantasia", ""),
            cnpj=cnpj,
            telefone=telefone,
            email=email.lower() if email else "",
            cidade=raw_data.get("municipio", ""),
            estado=raw_data.get("uf", ""),
            cnae=cnae_desc,
            porte=raw_data.get("porte", ""),
            site="",
            situacao=raw_data.get("situacao", ""),
            fonte="ReceitaWS",
        )
