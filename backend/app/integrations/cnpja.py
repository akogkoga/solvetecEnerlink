"""Adaptador real para CNPJá — consulta individual de CNPJ."""
import re
from typing import List, Optional
from app.integrations.base import BaseAPIAdapter
from app.models.schemas import FilterRequest, LeadNormalized
from app.core.config import CNPJA_URL, CNPJA_RATE_DELAY


class CNPJaAdapter(BaseAPIAdapter):
    """
    CNPJá (Open) — Provider de enriquecimento (fallback).
    Endpoint: GET https://open.cnpja.com/office/{cnpj}
    Rate limit: 5 req/min (delay de 12s entre chamadas).
    """

    PROVIDER_NAME = "CNPJa"
    RATE_DELAY = CNPJA_RATE_DELAY

    async def fetch_leads(self, filters: FilterRequest) -> List[dict]:
        """CNPJá não suporta busca por filtros — retorna lista vazia."""
        self.logger.info("CNPJá não suporta busca por filtros — ignorando")
        return []

    async def fetch_by_cnpj(self, cnpj: str) -> Optional[dict]:
        """Busca dados reais de uma empresa pelo CNPJ."""
        clean_cnpj = re.sub(r"\D", "", cnpj)
        url = f"{CNPJA_URL}/{clean_cnpj}"
        self.logger.info("Consultando CNPJ %s", clean_cnpj)

        response = await self._request_with_retry("GET", url)
        if response is None or response.status_code != 200:
            return None

        return response.json()

    def normalize(self, raw_data: dict) -> LeadNormalized:
        """Converte resposta do CNPJá para formato padrão."""
        company = raw_data.get("company", {}) or {}
        address = raw_data.get("address", {}) or {}
        phones = raw_data.get("phones", []) or []
        emails = raw_data.get("emails", []) or []
        activities = raw_data.get("mainActivity", {}) or {}
        registration = raw_data.get("registration", {}) or {}

        telefone = ""
        if phones and isinstance(phones, list):
            first = phones[0] if isinstance(phones[0], dict) else {}
            area = str(first.get("area", ""))
            number = str(first.get("number", ""))
            telefone = re.sub(r"\D", "", f"{area}{number}")

        email = ""
        if emails and isinstance(emails, list):
            first_email = emails[0]
            if isinstance(first_email, dict):
                email = first_email.get("address", "")
            elif isinstance(first_email, str):
                email = first_email

        cnae_desc = ""
        if isinstance(activities, dict):
            cnae_desc = activities.get("text", "") or activities.get("description", "")

        status = raw_data.get("status", {}) or {}
        status_text = status.get("text", "") if isinstance(status, dict) else str(status)
        situacao = registration.get("status", "") or status_text

        return LeadNormalized(
            empresa=company.get("name", "") or raw_data.get("alias", ""),
            cnpj=re.sub(r"\D", "", str(raw_data.get("taxId", ""))),
            telefone=telefone,
            email=email.lower() if email else "",
            cidade=address.get("city", "") or address.get("municipality", ""),
            estado=address.get("state", ""),
            cnae=cnae_desc,
            porte=company.get("size", {}).get("text", "") if isinstance(company.get("size"), dict) else "",
            site="",
            situacao=situacao,
            fonte="CNPJa",
        )
