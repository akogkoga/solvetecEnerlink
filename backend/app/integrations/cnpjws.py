"""Adaptador real para CNPJ.ws — consulta individual de CNPJ."""
import re
from typing import List, Optional
from app.integrations.base import BaseAPIAdapter
from app.models.schemas import FilterRequest, LeadNormalized
from app.core.config import CNPJWS_URL, CNPJWS_RATE_DELAY


class CNPJWSAdapter(BaseAPIAdapter):
    """
    CNPJ.ws (Pública) — Provider de enriquecimento (último fallback).
    Endpoint: GET https://publica.cnpj.ws/cnpj/{cnpj}
    Rate limit: Limitado (delay de 5s entre chamadas).
    """

    PROVIDER_NAME = "CNPJWS"
    RATE_DELAY = CNPJWS_RATE_DELAY

    async def fetch_leads(self, filters: FilterRequest) -> List[dict]:
        """CNPJ.ws não suporta busca por filtros — retorna lista vazia."""
        self.logger.info("CNPJ.ws não suporta busca por filtros — ignorando")
        return []

    async def fetch_by_cnpj(self, cnpj: str) -> Optional[dict]:
        """Busca dados reais de uma empresa pelo CNPJ."""
        clean_cnpj = re.sub(r"\D", "", cnpj)
        url = f"{CNPJWS_URL}/{clean_cnpj}"
        self.logger.info("Consultando CNPJ %s", clean_cnpj)

        response = await self._request_with_retry("GET", url)
        if response is None or response.status_code != 200:
            return None

        return response.json()

    def normalize(self, raw_data: dict) -> LeadNormalized:
        """Converte resposta do CNPJ.ws para formato padrão."""
        estabelecimento = raw_data.get("estabelecimento", {}) or {}
        cnpj = re.sub(r"\D", "", estabelecimento.get("cnpj", "") or "")
        if not cnpj:
            raiz = re.sub(r"\D", "", raw_data.get("cnpj_raiz", "") or "")
            ordem = re.sub(r"\D", "", estabelecimento.get("cnpj_ordem", "") or "")
            digito = re.sub(r"\D", "", estabelecimento.get("cnpj_digito_verificador", "") or "")
            cnpj = f"{raiz}{ordem}{digito}"

        telefone1 = estabelecimento.get("telefone1", "") or ""
        ddd1 = estabelecimento.get("ddd1", "") or ""
        telefone = re.sub(r"\D", "", f"{ddd1}{telefone1}")

        email = estabelecimento.get("email", "") or ""
        cidade_info = estabelecimento.get("cidade", {}) or {}
        cidade_nome = cidade_info.get("nome", "") if isinstance(cidade_info, dict) else str(cidade_info)

        estado_info = estabelecimento.get("estado", {}) or {}
        estado_sigla = estado_info.get("sigla", "") if isinstance(estado_info, dict) else str(estado_info)

        atividade = estabelecimento.get("atividade_principal", {}) or {}
        cnae_desc = atividade.get("descricao", "") if isinstance(atividade, dict) else ""

        situacao = estabelecimento.get("situacao_cadastral", "") or ""
        porte_info = raw_data.get("porte", {}) or {}
        porte = porte_info.get("descricao", "") if isinstance(porte_info, dict) else str(porte_info)

        return LeadNormalized(
            empresa=raw_data.get("razao_social", ""),
            cnpj=cnpj,
            telefone=telefone,
            email=email.lower() if email else "",
            cidade=cidade_nome,
            estado=estado_sigla,
            cnae=cnae_desc,
            porte=porte,
            site="",
            situacao=situacao,
            fonte="CNPJWS",
        )
