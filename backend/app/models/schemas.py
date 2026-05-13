"""Pydantic schemas for the lead generation API."""
import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class FilterRequest(BaseModel):
    termo: Optional[str] = Field(None, description="Free text search, for example tecnologia, marketing or contabilidade")
    nome: Optional[str] = Field(None, description="Company legal or trade name")
    cnae: Optional[str] = Field(None, description="Main or secondary CNAE code")
    estado: Optional[str] = Field(None, description="State UF, for example SP or RJ")
    cidade: Optional[str] = Field(None, description="City name")
    porte: Optional[str] = Field(None, description="Company size, for example ME, EPP, DEMAIS")
    natureza_juridica: Optional[str] = Field(None, description="Legal nature code or text")
    situacao: Optional[str] = Field(None, description="Registration status. Defaults to active when omitted")
    mei: Optional[bool] = Field(None, description="Filter companies opted into MEI")
    quantidade: Optional[int] = Field(100, description="Number of leads", ge=1, le=1000)
    pagina: Optional[int] = Field(1, description="Result page", ge=1, le=10000)

    @field_validator("cnae")
    @classmethod
    def normalize_cnae(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = re.sub(r"\D", "", value)
        return cleaned or None

    @field_validator("estado")
    @classmethod
    def normalize_estado(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().upper()
        return cleaned or None

    @field_validator("cidade", "porte", "termo", "nome", "natureza_juridica", "situacao")
    @classmethod
    def normalize_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class LeadNormalized(BaseModel):
    empresa: str
    cnpj: str
    telefone: Optional[str] = ""
    email: Optional[str] = ""
    cidade: Optional[str] = ""
    estado: Optional[str] = ""
    cnae: Optional[str] = ""
    porte: Optional[str] = ""
    site: Optional[str] = ""
    situacao: str = "ATIVA"
    fonte: str
    score: int = Field(0, description="Lead quality score, from 0 to 100")


class ProviderStatus(BaseModel):
    name: str
    status: str
    response_time_ms: Optional[int] = None
    error: Optional[str] = None


class LeadResponse(BaseModel):
    total_found: int
    total_returned: int
    leads: List[LeadNormalized]
    providers_used: List[str] = []
    search_time_ms: int = 0
    errors: List[str] = []
