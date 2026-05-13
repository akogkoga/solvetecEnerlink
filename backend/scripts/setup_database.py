"""Broad Receita Federal CNPJ ingestion into SQLite.

Examples:
  python scripts/setup_database.py --ufs RJ,MG,PR,BA,PE,RS --chunks all --force
  python scripts/setup_database.py --national --chunks all --force
  python scripts/setup_database.py --ufs SP,RJ --estab-chunks 1 --company-chunks all --limit 200000 --force

The script uses the official monthly RFB open-data directory and supports
national, multi-UF and incremental ingestion. External APIs are not used for
discovery; they remain enrichment-only in the application.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sqlite3
import sys
import time
import unicodedata
import zipfile
from pathlib import Path
from typing import Iterable

import httpx

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "empresas.db"
DOWNLOAD_DIR = DATA_DIR / "rfb_raw"

OFFICIAL_ROOT_URL = "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/"
MIRROR_ROOT_URL = "https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos/"
FALLBACK_BASE_URL = "https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos/2026-04-12/"
CHUNKS = list(range(10))
BATCH_SIZE = 5000

PORTE_MAP = {"00": "NAO INFORMADO", "01": "ME", "03": "EPP", "05": "DEMAIS"}
SITUACAO_MAP = {
    "01": "NULA",
    "02": "ATIVA",
    "03": "SUSPENSA",
    "04": "INAPTA",
    "08": "BAIXADA",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Enerlink/1.0"
}


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.upper().strip()


def digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def parse_chunks(value: str | None, default: list[int]) -> list[int]:
    if not value or value.lower() == "all":
        return default
    chunks = sorted({int(part.strip()) for part in value.split(",") if part.strip()})
    invalid = [chunk for chunk in chunks if chunk not in CHUNKS]
    if invalid:
        raise ValueError(f"Invalid chunks: {invalid}. Use 0-9 or all.")
    return chunks


def parse_ufs(value: str | None, national: bool) -> set[str]:
    env_uf = os.environ.get("RFB_TARGET_UF") or os.environ.get("RFB_TARGET_UFS")
    raw = value or env_uf or ""
    if national or not raw:
        return set()
    return {uf.strip().upper() for uf in raw.split(",") if uf.strip()}


def discover_latest_base_url() -> str:
    configured = os.environ.get("RFB_BASE_URL")
    if configured:
        return configured.rstrip("/") + "/"

    for root in (OFFICIAL_ROOT_URL, MIRROR_ROOT_URL):
        try:
            resp = httpx.get(root, headers=HEADERS, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            months = sorted(set(re.findall(r'href="(20\d{2}(?:-\d{2}){1,2})/"', resp.text)))
            if months:
                return f"{root}{months[-1]}/"
        except Exception as exc:
            print(f"  Aviso: nao foi possivel descobrir mes em {root} ({exc}).")
    return FALLBACK_BASE_URL


def download_file(url: str, dest: Path, retries: int = 3) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  existe: {dest.name}")
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    for attempt in range(1, retries + 1):
        try:
            print(f"  baixando: {url}")
            with httpx.stream("GET", url, headers=HEADERS, timeout=180, follow_redirects=True) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", "0") or 0)
                downloaded = 0
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded / total * 100
                            sys.stdout.write(f"\r    {downloaded/1024/1024:.0f}MB / {total/1024/1024:.0f}MB ({pct:.0f}%)")
                            sys.stdout.flush()
            tmp.replace(dest)
            print(f"\n    OK: {dest.name}")
            return
        except Exception as exc:
            print(f"\n    erro tentativa {attempt}/{retries}: {exc}")
            if tmp.exists():
                tmp.unlink()
            if attempt == retries:
                raise
            time.sleep(5)


def zip_csv_reader(zip_path: Path) -> tuple[csv.reader, zipfile.ZipFile]:
    zf = zipfile.ZipFile(zip_path, "r")
    names = [name for name in zf.namelist() if not name.endswith("/")]
    csv_name = next((name for name in names if name.lower().endswith(".csv")), names[0])
    raw = zf.open(csv_name)
    text = io.TextIOWrapper(raw, encoding="latin-1", errors="replace", newline="")
    return csv.reader(text, delimiter=";"), zf


def load_lookup(path: Path) -> dict[str, str]:
    reader, zf = zip_csv_reader(path)
    try:
        return {row[0].strip(): row[1].strip() for row in reader if len(row) >= 2}
    finally:
        zf.close()


def connect_db(force: bool) -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if force and DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-200000")
    create_schema(conn)
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS empresas_base (
            cnpj_basico TEXT PRIMARY KEY,
            razao_social TEXT,
            razao_social_norm TEXT,
            natureza_juridica_codigo TEXT,
            porte_codigo TEXT,
            porte TEXT,
            capital_social TEXT
        );

        CREATE TABLE IF NOT EXISTS simples (
            cnpj_basico TEXT PRIMARY KEY,
            opcao_pelo_simples INTEGER,
            opcao_pelo_mei INTEGER
        );

        CREATE TABLE IF NOT EXISTS empresas (
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
            fonte TEXT DEFAULT 'ReceitaFederal',
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS ingestion_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()


def create_indexes(conn: sqlite3.Connection) -> None:
    print("  criando indices...")
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
        CREATE INDEX IF NOT EXISTS idx_empresas_uf_quality ON empresas(uf, quality_score DESC);
        CREATE INDEX IF NOT EXISTS idx_empresas_uf_situacao_quality ON empresas(uf, situacao_codigo, quality_score DESC);
        CREATE INDEX IF NOT EXISTS idx_empresas_uf_mun_quality ON empresas(uf, municipio_norm, quality_score DESC);
        CREATE INDEX IF NOT EXISTS idx_empresas_uf_cnae_quality ON empresas(uf, cnae_fiscal, quality_score DESC);
    """)
    conn.execute("ANALYZE empresas")
    conn.commit()


def import_empresas_base(conn: sqlite3.Connection, files: list[Path]) -> int:
    total = 0
    for path in files:
        print(f"  empresas base: {path.name}")
        reader, zf = zip_csv_reader(path)
        batch = []
        try:
            for row in reader:
                if len(row) < 6:
                    continue
                porte_code = row[5].strip()
                batch.append((
                    row[0].strip(),
                    row[1].strip(),
                    norm(row[1]),
                    row[2].strip(),
                    porte_code,
                    PORTE_MAP.get(porte_code, porte_code),
                    row[4].strip(),
                ))
                if len(batch) >= BATCH_SIZE:
                    conn.executemany("INSERT OR REPLACE INTO empresas_base VALUES (?,?,?,?,?,?,?)", batch)
                    total += len(batch)
                    batch.clear()
            if batch:
                conn.executemany("INSERT OR REPLACE INTO empresas_base VALUES (?,?,?,?,?,?,?)", batch)
                total += len(batch)
            conn.commit()
        finally:
            zf.close()
        print(f"    bases importadas acumuladas: {total:,}")
    return total


def import_simples(conn: sqlite3.Connection, path: Path) -> int:
    if not path.exists():
        print("  Simples.zip ausente; MEI/Simples ficarao como 0")
        return 0
    print("  simples/MEI")
    reader, zf = zip_csv_reader(path)
    total = 0
    batch = []
    try:
        for row in reader:
            if len(row) < 6:
                continue
            batch.append((
                row[0].strip(),
                1 if row[1].strip().upper() == "S" else 0,
                1 if row[4].strip().upper() == "S" else 0,
            ))
            if len(batch) >= BATCH_SIZE:
                conn.executemany("INSERT OR REPLACE INTO simples VALUES (?,?,?)", batch)
                total += len(batch)
                batch.clear()
        if batch:
            conn.executemany("INSERT OR REPLACE INTO simples VALUES (?,?,?)", batch)
            total += len(batch)
        conn.commit()
    finally:
        zf.close()
    print(f"    simples importados: {total:,}")
    return total


def fetch_map(conn: sqlite3.Connection, table: str, keys: Iterable[str]) -> dict[str, sqlite3.Row]:
    unique = sorted(set(keys))
    result: dict[str, sqlite3.Row] = {}
    if not unique:
        return result
    conn.row_factory = sqlite3.Row
    for start in range(0, len(unique), 900):
        part = unique[start:start + 900]
        placeholders = ",".join("?" for _ in part)
        for row in conn.execute(f"SELECT * FROM {table} WHERE cnpj_basico IN ({placeholders})", part):
            result[row["cnpj_basico"]] = row
    return result


def quality_score(row: dict) -> int:
    return min(100, sum([
        25 if row["situacao_codigo"] == "02" else 0,
        22 if row["telefone"] else 0,
        18 if row["email"] else 0,
        20 if all([row["razao_social"], row["cnpj"], row["municipio"], row["uf"], row["cnae_fiscal"]]) else 0,
        5,
    ]))


def make_final_row(raw: list[str], base: sqlite3.Row | None, simple: sqlite3.Row | None, lookups: dict, now: str) -> tuple:
    cnpj_basico = raw[0].strip()
    cnpj = f"{cnpj_basico}{raw[1].strip()}{raw[2].strip()}"
    razao = (base["razao_social"] if base else "") or ""
    razao_norm = (base["razao_social_norm"] if base else norm(razao)) or norm(razao)
    fantasia = raw[4].strip()
    cnae = raw[11].strip()
    cnae_desc = lookups["cnaes"].get(cnae, "")
    municipio_code = raw[20].strip()
    municipio = lookups["municipios"].get(municipio_code, municipio_code)
    situacao_code = raw[5].strip()
    situacao = SITUACAO_MAP.get(situacao_code, situacao_code)
    porte_code = (base["porte_codigo"] if base else "") or ""
    mei = int(simple["opcao_pelo_mei"]) if simple else 0
    simples = int(simple["opcao_pelo_simples"]) if simple else 0
    porte = "MEI" if mei else ((base["porte"] if base else "") or PORTE_MAP.get(porte_code, porte_code))
    natureza_code = (base["natureza_juridica_codigo"] if base else "") or ""
    natureza = lookups["naturezas"].get(natureza_code, natureza_code)
    ddd1, tel1 = raw[21].strip(), raw[22].strip()
    ddd2, tel2 = raw[23].strip(), raw[24].strip()
    telefone = f"{ddd1}{tel1}" if ddd1 and tel1 else (f"{ddd2}{tel2}" if ddd2 and tel2 else "")
    email = raw[27].strip().lower() if len(raw) > 27 else ""
    logradouro = " ".join(part for part in [raw[13].strip(), raw[14].strip(), raw[15].strip()] if part)
    search_text = norm(" ".join([razao, fantasia, cnae_desc, municipio, natureza, porte, raw[17].strip(), raw[19].strip()]))
    row = {
        "cnpj": cnpj,
        "razao_social": razao,
        "municipio": municipio,
        "uf": raw[19].strip().upper(),
        "cnae_fiscal": cnae,
        "situacao_codigo": situacao_code,
        "telefone": telefone,
        "email": email,
    }
    return (
        cnpj, cnpj_basico, razao, razao_norm, fantasia, norm(fantasia),
        cnae, cnae_desc, norm(cnae_desc), raw[19].strip().upper(),
        municipio_code, municipio, norm(municipio), situacao_code, situacao, norm(situacao),
        porte_code, porte, norm(porte), natureza_code, natureza, norm(natureza),
        telefone, email, raw[17].strip(), raw[18].strip(), logradouro,
        mei, simples, search_text, quality_score(row), "ReceitaFederal", now,
    )


def import_estabelecimentos(conn: sqlite3.Connection, files: list[Path], lookups: dict, ufs: set[str], situacoes: set[str], limit: int | None) -> int:
    inserted = 0
    scanned = 0
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    for path in files:
        print(f"  estabelecimentos: {path.name}")
        reader, zf = zip_csv_reader(path)
        raw_batch: list[list[str]] = []
        try:
            for row in reader:
                scanned += 1
                if len(row) < 28:
                    continue
                uf = row[19].strip().upper()
                situacao = row[5].strip()
                if ufs and uf not in ufs:
                    continue
                if situacoes and situacao not in situacoes:
                    continue
                raw_batch.append(row)
                if len(raw_batch) >= BATCH_SIZE:
                    inserted += flush_estab_batch(conn, raw_batch, lookups, now)
                    raw_batch.clear()
                if limit and inserted >= limit:
                    break
            if raw_batch and (not limit or inserted < limit):
                inserted += flush_estab_batch(conn, raw_batch, lookups, now)
                raw_batch.clear()
            conn.commit()
        finally:
            zf.close()
        print(f"    escaneados: {scanned:,} | inseridos: {inserted:,}")
        if limit and inserted >= limit:
            break
    return inserted


def flush_estab_batch(conn: sqlite3.Connection, raw_batch: list[list[str]], lookups: dict, now: str) -> int:
    bases = [row[0].strip() for row in raw_batch]
    base_map = fetch_map(conn, "empresas_base", bases)
    simples_map = fetch_map(conn, "simples", bases)
    rows = [
        make_final_row(row, base_map.get(row[0].strip()), simples_map.get(row[0].strip()), lookups, now)
        for row in raw_batch
    ]
    conn.executemany("""
        INSERT OR REPLACE INTO empresas VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
    """, rows)
    return len(rows)


def required_files(base_url: str, company_chunks: list[int], estab_chunks: list[int], include_simples: bool) -> dict[str, str]:
    files = {
        "Municipios.zip": f"{base_url}Municipios.zip",
        "Cnaes.zip": f"{base_url}Cnaes.zip",
        "Naturezas.zip": f"{base_url}Naturezas.zip",
    }
    if include_simples:
        files["Simples.zip"] = f"{base_url}Simples.zip"
    for chunk in company_chunks:
        files[f"Empresas{chunk}.zip"] = f"{base_url}Empresas{chunk}.zip"
    for chunk in estab_chunks:
        files[f"Estabelecimentos{chunk}.zip"] = f"{base_url}Estabelecimentos{chunk}.zip"
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Receita Federal CNPJ data into SQLite")
    parser.add_argument("--base-url", help="RFB monthly URL. Defaults to latest official directory.")
    parser.add_argument("--ufs", help="Comma-separated UF list, for example SP,RJ,MG. Empty means national.")
    parser.add_argument("--national", action="store_true", help="Import every UF.")
    parser.add_argument("--chunks", default="all", help="Shortcut for company and establishment chunks: 0-9 or all.")
    parser.add_argument("--company-chunks", help="Empresas chunks, defaults to --chunks.")
    parser.add_argument("--estab-chunks", help="Estabelecimentos chunks, defaults to --chunks.")
    parser.add_argument("--all-situations", action="store_true", help="Import every registration status. Default imports active only.")
    parser.add_argument("--situacoes", default="02", help="Comma-separated status codes. Default: 02 active.")
    parser.add_argument("--limit", type=int, help="Maximum inserted establishments for smoke tests.")
    parser.add_argument("--force", action="store_true", help="Recreate database from scratch.")
    parser.add_argument("--skip-download", action="store_true", help="Use files already present in data/rfb_raw.")
    parser.add_argument("--skip-simples", action="store_true", help="Skip Simples.zip/MEI import.")
    args = parser.parse_args()

    t0 = time.time()
    base_url = (args.base_url or discover_latest_base_url()).rstrip("/") + "/"
    chunks = parse_chunks(args.chunks, CHUNKS)
    company_chunks = parse_chunks(args.company_chunks, chunks)
    estab_chunks = parse_chunks(args.estab_chunks, chunks)
    ufs = parse_ufs(args.ufs, args.national)
    situacoes = set() if args.all_situations else {s.strip() for s in args.situacoes.split(",") if s.strip()}
    include_simples = not args.skip_simples

    print("=" * 72)
    print("  Receita Federal CNPJ -> SQLite")
    print(f"  Base URL: {base_url}")
    print(f"  UFs: {'NACIONAL' if not ufs else ','.join(sorted(ufs))}")
    print(f"  Empresas chunks: {company_chunks}")
    print(f"  Estabelecimentos chunks: {estab_chunks}")
    print(f"  Situacoes: {'TODAS' if not situacoes else ','.join(sorted(situacoes))}")
    print(f"  DB: {DB_PATH}")
    print("=" * 72)

    files = required_files(base_url, company_chunks, estab_chunks, include_simples)
    if not args.skip_download:
        print("\n[1/6] Download")
        for filename, url in files.items():
            download_file(url, DOWNLOAD_DIR / filename)
    else:
        print("\n[1/6] Download pulado")

    print("\n[2/6] Lookups")
    lookups = {
        "municipios": load_lookup(DOWNLOAD_DIR / "Municipios.zip"),
        "cnaes": load_lookup(DOWNLOAD_DIR / "Cnaes.zip"),
        "naturezas": load_lookup(DOWNLOAD_DIR / "Naturezas.zip"),
    }
    print(f"  municipios={len(lookups['municipios'])} cnaes={len(lookups['cnaes'])} naturezas={len(lookups['naturezas'])}")

    print("\n[3/6] Schema")
    conn = connect_db(force=args.force)

    print("\n[4/6] Empresas base")
    company_files = [DOWNLOAD_DIR / f"Empresas{chunk}.zip" for chunk in company_chunks]
    import_empresas_base(conn, company_files)

    print("\n[5/6] Simples/MEI")
    if include_simples:
        import_simples(conn, DOWNLOAD_DIR / "Simples.zip")
    else:
        print("  pulado")

    print("\n[6/6] Estabelecimentos")
    estab_files = [DOWNLOAD_DIR / f"Estabelecimentos{chunk}.zip" for chunk in estab_chunks]
    total = import_estabelecimentos(conn, estab_files, lookups, ufs, situacoes, args.limit)

    conn.execute("INSERT OR REPLACE INTO ingestion_meta VALUES (?,?)", ("base_url", base_url))
    conn.execute("INSERT OR REPLACE INTO ingestion_meta VALUES (?,?)", ("updated_at", time.strftime("%Y-%m-%dT%H:%M:%S")))
    conn.execute("INSERT OR REPLACE INTO ingestion_meta VALUES (?,?)", ("ufs", "NACIONAL" if not ufs else ",".join(sorted(ufs))))
    conn.execute("INSERT OR REPLACE INTO ingestion_meta VALUES (?,?)", ("estab_chunks", ",".join(map(str, estab_chunks))))
    conn.execute("INSERT OR REPLACE INTO ingestion_meta VALUES (?,?)", ("company_chunks", ",".join(map(str, company_chunks))))
    conn.execute("INSERT OR REPLACE INTO ingestion_meta VALUES (?,?)", ("limit", str(args.limit or "")))
    conn.execute("INSERT OR REPLACE INTO ingestion_meta VALUES (?,?)", ("status", "indexing"))
    conn.commit()

    create_indexes(conn)
    conn.execute("INSERT OR REPLACE INTO ingestion_meta VALUES (?,?)", ("status", "completed"))
    conn.execute("INSERT OR REPLACE INTO ingestion_meta VALUES (?,?)", ("completed_at", time.strftime("%Y-%m-%dT%H:%M:%S")))
    conn.execute("INSERT OR REPLACE INTO ingestion_meta VALUES (?,?)", ("total_empresas", str(conn.execute("SELECT COUNT(*) FROM empresas").fetchone()[0])))
    conn.commit()

    by_uf = conn.execute("SELECT uf, COUNT(*) FROM empresas GROUP BY uf ORDER BY uf").fetchall()
    count = conn.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
    conn.close()

    elapsed = time.time() - t0
    print("\n" + "=" * 72)
    print(f"  Concluido em {elapsed/60:.1f} min")
    print(f"  Inseridos nesta execucao: {total:,}")
    print(f"  Total no banco: {count:,}")
    print(f"  DB: {DB_PATH} ({DB_PATH.stat().st_size/1024/1024:.0f}MB)")
    print("  Por UF:", ", ".join(f"{uf}:{qty}" for uf, qty in by_uf[:27]))
    print("=" * 72)


if __name__ == "__main__":
    main()
