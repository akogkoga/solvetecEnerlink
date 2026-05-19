"""Generic local SQLite discovery provider for Receita Federal data."""
import logging
import os
import re
import sqlite3
import time
import unicodedata
from pathlib import Path
from typing import List, Optional

from app.integrations.base import BaseAPIAdapter
from app.models.schemas import FilterRequest, LeadNormalized
from app.services.health_tracker import health_tracker

logger = logging.getLogger("provider.SQLiteLocal")

DB_PATH = Path(
    os.environ.get(
        "SQLITE_DB_PATH",
        Path(__file__).parent.parent.parent / "data" / "empresas.db",
    )
)
REQUIRED_COLUMNS = {
    "cnpj", "razao_social", "cnae_fiscal", "uf", "municipio",
    "situacao", "porte", "telefone", "email",
}


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.upper().strip()


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _cnae_prefix(value: str) -> str:
    clean = _digits(value)
    return clean[:-2] if clean.endswith("00") and len(clean) >= 4 else clean


def _term_prefixes(term: Optional[str]) -> list[str]:
    normalized = _normalize(term)
    mapping = {
        "TECNOLOGIA": ["62015", "62023", "62031", "62040", "62091", "63194"],
        "TECNOLOGIAS": ["62015", "62023", "62031", "62040", "62091", "63194"],
        "TECH": ["62015", "62023", "62031", "62040", "62091", "63194"],
        "SOFTWARE": ["62015", "62023", "62031"],
        "SISTEMAS": ["62015", "62023", "62031", "62040"],
        "SERVICO": ["62", "63", "69", "70", "73", "74", "77", "78", "80", "81", "82"],
        "SERVICOS": ["62", "63", "69", "70", "73", "74", "77", "78", "80", "81", "82"],
        "COMERCIO": ["45", "46", "47"],
        "COMERCIAL": ["45", "46", "47"],
        "MARKETING": ["73114", "73190"],
        "PUBLICIDADE": ["73114", "73190"],
        "CONTABILIDADE": ["69206"],
        "CONTABIL": ["69206"],
        "MERCADO": ["47113", "47121"],
        "SUPERMERCADO": ["47113"],
        "RESTAURANTE": ["56112"],
        "RESTAURANTES": ["56112"],
        "CLINICA": ["86305", "86101", "86500"],
        "CLINICAS": ["86305", "86101", "86500"],
        "INDUSTRIA": ["10", "11", "13", "14", "15", "16", "17", "18", "20", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32"],
        "FABRICA": ["10", "11", "13", "14", "15", "16", "17", "18", "20", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32"],
    }
    return mapping.get(normalized, [])


def _term_tokens(term: Optional[str]) -> list[str]:
    normalized = _normalize(term)
    tokens = [token for token in re.split(r"[^A-Z0-9]+", normalized) if len(token) >= 4]
    ignored = {"PARA", "COM", "DAS", "DOS", "EMPRESA", "EMPRESAS", "SERVICO", "SERVICOS"}
    return [token for token in tokens if token not in ignored][:4]


class SQLiteDiscoveryProvider(BaseAPIAdapter):
    """Fast, paginated local discovery over a broad CNPJ SQLite database."""

    PROVIDER_NAME = "SQLiteLocal"
    RATE_DELAY = 0

    def __init__(self):
        super().__init__()
        self._conn: Optional[sqlite3.Connection] = None
        self._schema_checked = False

    def _get_conn(self) -> Optional[sqlite3.Connection]:
        if self._conn is not None:
            return self._conn

        if not DB_PATH.exists():
            self.logger.warning("DB not found: %s", DB_PATH)
            health_tracker.record_failure(self.PROVIDER_NAME, "database not found")
            return None

        try:
            self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute("PRAGMA query_only=ON")
            self._validate_schema(self._conn)
            count = self._conn.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
            self.logger.info("SQLite connected: %s companies", f"{count:,}")
            return self._conn
        except Exception as exc:
            self.logger.error("SQLite unavailable: %s", exc)
            health_tracker.record_failure(self.PROVIDER_NAME, str(exc))
            self._conn = None
            return None

    def _validate_schema(self, conn: sqlite3.Connection) -> None:
        if self._schema_checked:
            return
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='empresas'"
        ).fetchone()
        if table is None:
            raise RuntimeError("table empresas not found")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(empresas)").fetchall()}
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise RuntimeError(f"invalid schema, missing columns: {', '.join(sorted(missing))}")
        self._schema_checked = True

    async def fetch_leads(self, filters: FilterRequest) -> List[dict]:
        start = time.monotonic()
        conn = self._get_conn()
        if conn is None:
            return []

        query, params = self._build_query(filters)
        try:
            rows = conn.execute(query, params).fetchall()
            elapsed_ms = (time.monotonic() - start) * 1000
            health_tracker.record_success(self.PROVIDER_NAME, elapsed_ms)
            self.logger.info("SQLite returned %d leads in %.0fms", len(rows), elapsed_ms)
            return [dict(row) for row in rows]
        except Exception as exc:
            self.logger.error("SQLite query error: %s", exc)
            health_tracker.record_failure(self.PROVIDER_NAME, str(exc))
            return []

    @staticmethod
    def _build_query(filters: FilterRequest) -> tuple[str, list]:
        conditions: list[str] = []
        params: list = []

        situacao = _normalize(filters.situacao)
        if situacao and situacao not in {"TODAS", "TODOS", "ALL", "*"}:
            if situacao in {"ATIVA", "02"}:
                conditions.append("situacao_codigo = '02'")
            else:
                conditions.append("(situacao_norm LIKE ? OR situacao_codigo = ?)")
                params.extend([f"%{situacao}%", situacao])
        elif not situacao:
            conditions.append("situacao_codigo = '02'")

        if filters.estado:
            conditions.append("uf = ?")
            params.append(filters.estado.upper())

        if filters.cidade:
            conditions.append("municipio_norm LIKE ?")
            params.append(f"%{_normalize(filters.cidade)}%")

        if filters.cnae:
            conditions.append("cnae_fiscal LIKE ?")
            params.append(f"{_cnae_prefix(filters.cnae)}%")

        if filters.nome:
            needle = _normalize(filters.nome)
            conditions.append("(razao_social_norm LIKE ? OR nome_fantasia_norm LIKE ?)")
            params.extend([f"%{needle}%", f"%{needle}%"])

        if filters.natureza_juridica:
            nature = _normalize(filters.natureza_juridica)
            nature_digits = _digits(filters.natureza_juridica)
            if nature_digits:
                conditions.append("natureza_juridica_codigo = ?")
                params.append(nature_digits)
            else:
                conditions.append("natureza_juridica_norm LIKE ?")
                params.append(f"%{nature}%")

        if filters.mei is not None:
            conditions.append("opcao_pelo_mei = ?")
            params.append(1 if filters.mei else 0)

        if filters.porte:
            porte = _normalize(filters.porte)
            if porte == "MEI":
                conditions.append("opcao_pelo_mei = 1")
            else:
                conditions.append("porte_norm LIKE ?")
                params.append(f"%{porte}%")

        if filters.termo:
            term = _normalize(filters.termo)
            term_conditions = ["search_text LIKE ?"]
            term_params = [f"%{term}%"]

            for prefix in _term_prefixes(filters.termo):
                term_conditions.append("cnae_fiscal LIKE ?")
                term_params.append(f"{prefix}%")

            for token in _term_tokens(filters.termo):
                if token != term:
                    term_conditions.append("search_text LIKE ?")
                    term_params.append(f"%{token}%")

            if term == "MEI":
                term_conditions.append("opcao_pelo_mei = 1")
            if term == "LTDA":
                term_conditions.append("natureza_juridica_norm LIKE ?")
                term_params.append("%LIMITADA%")

            conditions.append("(" + " OR ".join(term_conditions) + ")")
            params.extend(term_params)

        limit = filters.quantidade or 100
        offset = ((filters.pagina or 1) - 1) * limit
        where = " AND ".join(conditions) if conditions else "1 = 1"
        query = (
            "SELECT * FROM empresas "
            f"WHERE {where} "
            "ORDER BY "
            "quality_score DESC, "
            "CASE WHEN COALESCE(nome_fantasia_norm, '') <> '' THEN 0 ELSE 1 END, "
            "CASE WHEN natureza_juridica_norm LIKE '%LIMITADA%' THEN 0 ELSE 1 END, "
            "CASE WHEN COALESCE(telefone, '') <> '' THEN 0 ELSE 1 END, "
            "CASE WHEN COALESCE(email, '') <> '' THEN 0 ELSE 1 END, "
            "razao_social_norm "
            "LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        return query, params

    def normalize(self, raw_data: dict) -> LeadNormalized:
        raw_phone = str(raw_data.get("telefone", "") or "")
        telefone = raw_phone.strip() if "*" in raw_phone else _digits(raw_phone)
        situacao = raw_data.get("situacao", "") or raw_data.get("situacao_codigo", "") or "ATIVA"
        nome_fantasia = (raw_data.get("nome_fantasia", "") or "").strip()
        razao_social = (raw_data.get("razao_social", "") or "").strip()

        return LeadNormalized(
            empresa=nome_fantasia or razao_social,
            cnpj=_digits(raw_data.get("cnpj")),
            telefone=telefone,
            email=(raw_data.get("email", "") or "").lower().strip(),
            cidade=raw_data.get("municipio", "") or "",
            estado=(raw_data.get("uf", "") or "").upper(),
            cnae=raw_data.get("cnae_fiscal", "") or raw_data.get("cnae_descricao", "") or "",
            porte=raw_data.get("porte", "") or "",
            site=raw_data.get("site", "") or "",
            situacao=situacao,
            fonte="SQLiteLocal",
        )

    @property
    def is_available(self) -> bool:
        return DB_PATH.exists()

    @property
    def total_companies(self) -> int:
        conn = self._get_conn()
        if conn is None:
            return 0
        return conn.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
