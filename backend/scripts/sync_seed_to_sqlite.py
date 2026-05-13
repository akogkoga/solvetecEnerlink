"""Create a local SQLite database from the curated seed dataset."""
import json
import re
import sqlite3
import time
import unicodedata
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SEED_FILE = DATA_DIR / "seed_cnpjs.json"
DB_PATH = DATA_DIR / "empresas.db"


def digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.upper().strip()


def load_companies() -> list[dict]:
    payload = json.loads(SEED_FILE.read_text(encoding="utf-8-sig"))
    companies = payload.get("companies", []) if isinstance(payload, dict) else payload
    return [item for item in companies if isinstance(item, dict) and len(digits(item.get("cnpj"))) == 14]


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        DROP TABLE IF EXISTS empresas;
        CREATE TABLE empresas (
            cnpj TEXT PRIMARY KEY,
            cnpj_basico TEXT,
            razao_social TEXT NOT NULL,
            razao_social_norm TEXT,
            nome_fantasia TEXT,
            nome_fantasia_norm TEXT,
            cnae_fiscal TEXT,
            cnae_descricao TEXT,
            cnae_descricao_norm TEXT,
            uf TEXT,
            municipio_codigo TEXT,
            municipio TEXT,
            municipio_norm TEXT,
            situacao_codigo TEXT,
            situacao TEXT,
            situacao_norm TEXT,
            porte_codigo TEXT,
            porte TEXT,
            porte_norm TEXT,
            natureza_juridica_codigo TEXT,
            natureza_juridica TEXT,
            natureza_juridica_norm TEXT,
            telefone TEXT,
            email TEXT,
            bairro TEXT,
            cep TEXT,
            logradouro TEXT,
            opcao_pelo_mei INTEGER DEFAULT 0,
            opcao_pelo_simples INTEGER DEFAULT 0,
            search_text TEXT,
            quality_score INTEGER DEFAULT 0,
            fonte TEXT DEFAULT 'SeedDataset',
            updated_at TEXT
        );
    """)


def quality(row: dict) -> int:
    return min(100, sum([
        25 if row["situacao_codigo"] == "02" else 0,
        22 if digits(row["telefone"]) or "*" in row["telefone"] else 0,
        18 if "@" in row["email"] or "*" in row["email"] else 0,
        20 if row["razao_social"] and row["cnpj"] and row["municipio"] and row["uf"] and row["cnae_fiscal"] else 0,
        10 if row.get("site") else 0,
        5,
    ]))


def create_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_empresas_uf ON empresas(uf);
        CREATE INDEX IF NOT EXISTS idx_empresas_uf_mun ON empresas(uf, municipio_norm);
        CREATE INDEX IF NOT EXISTS idx_empresas_cnae ON empresas(cnae_fiscal);
        CREATE INDEX IF NOT EXISTS idx_empresas_porte ON empresas(porte_norm);
        CREATE INDEX IF NOT EXISTS idx_empresas_situacao ON empresas(situacao_codigo);
        CREATE INDEX IF NOT EXISTS idx_empresas_natureza ON empresas(natureza_juridica_codigo);
        CREATE INDEX IF NOT EXISTS idx_empresas_mei ON empresas(opcao_pelo_mei);
        CREATE INDEX IF NOT EXISTS idx_empresas_nome ON empresas(razao_social_norm);
        CREATE INDEX IF NOT EXISTS idx_empresas_quality ON empresas(quality_score DESC);
    """)
    conn.commit()


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    companies = load_companies()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    create_schema(conn)

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    rows = []
    for item in companies:
        cnpj = digits(item.get("cnpj"))
        razao = item.get("razao_social", "") or item.get("nome_fantasia", "")
        fantasia = item.get("nome_fantasia", "") or ""
        municipio = (item.get("municipio", "") or "").upper()
        situacao = item.get("descricao_situacao_cadastral", "") or item.get("situacao", "") or "ATIVA"
        mei = 1 if item.get("opcao_pelo_mei") else 0
        porte = "MEI" if mei else (item.get("porte", "") or "")
        natureza = item.get("natureza_juridica", "") or ""
        cnae_desc = item.get("cnae_fiscal_descricao", "") or ""
        telefone = str(item.get("telefone") or item.get("ddd_telefone_1") or item.get("telefone_publico") or "").strip()
        email = (item.get("email", "") or item.get("email_publico", "") or "").lower()
        row = {
            "cnpj": cnpj,
            "situacao_codigo": "02" if "ATIVA" in norm(situacao) else "",
            "telefone": telefone,
            "email": email,
            "razao_social": razao,
            "municipio": municipio,
            "uf": (item.get("uf", "") or "").upper(),
            "cnae_fiscal": digits(item.get("cnae_fiscal")),
            "site": item.get("site", "") or "",
        }
        search_text = norm(" ".join([
            razao, fantasia, cnae_desc, natureza, porte,
            item.get("termos", "") or "", municipio, item.get("uf", "") or "",
        ]))
        score = quality(row)
        rows.append((
            cnpj, cnpj[:8], razao, norm(razao), fantasia, norm(fantasia),
            digits(item.get("cnae_fiscal")), cnae_desc, norm(cnae_desc),
            row["uf"], str(item.get("codigo_municipio", "") or ""), municipio, norm(municipio),
            row["situacao_codigo"], situacao, norm(situacao),
            "", porte, norm(porte),
            digits(item.get("codigo_natureza_juridica")), natureza, norm(natureza),
            telefone, email, item.get("bairro", "") or "", digits(item.get("cep")),
            item.get("logradouro", "") or "", mei, 0, search_text, score,
            "SeedDataset", now,
        ))

    conn.executemany("""
        INSERT OR REPLACE INTO empresas VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
    """, rows)
    create_indexes(conn)
    count = conn.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
    conn.close()
    print(f"SQLite local criado em {DB_PATH}")
    print(f"Empresas importadas: {count}")


if __name__ == "__main__":
    main()
