"""Build Seed MASSIVO — BrasilAPI CNPJ Scanner.

Escaneia CNPJs via BrasilAPI para construir um dataset local robusto.
Focado em empresas de SP com situação ATIVA.

Uso:
  cd backend
  .\\venv\\Scripts\\python.exe scripts\\build_seed.py
"""
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).parent.parent / "data"
SEED_FILE = DATA_DIR / "seed_cnpjs.json"

TARGET = 500
TARGET_UF = "SP"
CONCURRENCY = 15
BRASILAPI_URL = "https://brasilapi.com.br/api/cnpj/v1"

# Ranges de CNPJ espalhados para maximizar cobertura geográfica
START_BASES = [
    1_000_000, 2_000_000, 3_000_000, 4_000_000, 5_000_000,
    6_000_000, 7_000_000, 8_000_000, 9_000_000, 10_000_000,
    11_000_000, 12_000_000, 13_000_000, 14_000_000, 15_000_000,
    16_000_000, 17_000_000, 18_000_000, 19_000_000, 20_000_000,
    21_000_000, 22_000_000, 23_000_000, 24_000_000, 25_000_000,
    26_000_000, 27_000_000, 28_000_000, 29_000_000, 30_000_000,
    31_000_000, 33_000_000, 35_000_000, 37_000_000, 40_000_000,
    42_000_000, 45_000_000, 47_000_000, 50_000_000, 52_000_000,
    54_000_000, 56_000_000, 58_000_000, 60_000_000, 62_000_000,
    64_000_000, 66_000_000, 68_000_000, 70_000_000, 72_000_000,
]

SCAN_STEP = 37


def load_existing() -> list:
    """Carrega empresas já encontradas."""
    if not SEED_FILE.exists():
        return []
    try:
        data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
        return data.get("companies", []) if isinstance(data, dict) else data
    except Exception:
        return []


def save_dataset(companies: list) -> None:
    """Salva dataset em JSON."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "total": len(companies),
            "target_uf": TARGET_UF,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        "companies": companies,
    }
    SEED_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def fetch_cnpj(client: httpx.AsyncClient, cnpj: str) -> dict | None:
    """Busca um CNPJ na BrasilAPI."""
    try:
        resp = await client.get(f"{BRASILAPI_URL}/{cnpj}", timeout=8)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def is_valid_company(data: dict) -> bool:
    """Verifica se é empresa ativa do estado alvo."""
    uf = (data.get("uf") or "").upper()
    situacao = data.get("descricao_situacao_cadastral", "")
    if isinstance(situacao, str):
        situacao = situacao.upper()
    else:
        situacao = str(data.get("situacao_cadastral", ""))

    is_active = situacao in ("ATIVA", "2", "02") or "ATIVA" in str(situacao)
    is_target_uf = (not TARGET_UF) or uf == TARGET_UF.upper()
    return is_active and is_target_uf


async def scan_range(
    client: httpx.AsyncClient, base: int,
    companies: list, seen: set, max_offset: int = 50_000,
) -> int:
    """Escaneia range de CNPJs a partir de um base."""
    found = 0
    offset = 0

    while offset < max_offset and len(companies) < TARGET:
        batch_cnpjs = []
        for i in range(CONCURRENCY):
            cnpj_num = base + offset + (i * SCAN_STEP)
            cnpj_str = f"{cnpj_num:08d}000100"
            if cnpj_str not in seen:
                batch_cnpjs.append(cnpj_str)

        if not batch_cnpjs:
            offset += CONCURRENCY * SCAN_STEP
            continue

        tasks = [fetch_cnpj(client, c) for c in batch_cnpjs]
        results = await asyncio.gather(*tasks)

        for data in results:
            if data and is_valid_company(data):
                cnpj = str(data.get("cnpj", ""))
                if cnpj not in seen:
                    companies.append(data)
                    seen.add(cnpj)
                    found += 1

        offset += CONCURRENCY * SCAN_STEP

    return found


async def main():
    """Scanner principal."""
    companies = load_existing()
    seen = {str(c.get("cnpj", "")) for c in companies}

    print("=" * 60)
    print("  Build Seed — BrasilAPI CNPJ Scanner (MASSIVO)")
    print(f"  Meta: {TARGET} empresas de {TARGET_UF or 'BR'}")
    print(f"  Existentes: {len(companies)}")
    print(f"  Concorrência: {CONCURRENCY}")
    print(f"  Ranges: {len(START_BASES)}")
    print("=" * 60)

    if len(companies) >= TARGET:
        print(f"  Meta já atingida: {len(companies)} empresas")
        return

    t0 = time.time()
    scanned_total = 0

    async with httpx.AsyncClient() as client:
        for idx, base in enumerate(START_BASES):
            if len(companies) >= TARGET:
                break

            found = await scan_range(client, base, companies, seen)
            scanned_total += CONCURRENCY * (50_000 // (CONCURRENCY * SCAN_STEP))

            elapsed = time.time() - t0
            rate = scanned_total / elapsed if elapsed > 0 else 0

            sys.stdout.write(
                f"\r  Range {idx+1}/{len(START_BASES)} | "
                f"Base: {base:,} | "
                f"Novas: {found} | "
                f"Total: {len(companies)} | "
                f"Vel: {rate:.0f}/s"
            )
            sys.stdout.flush()

            # Salva progresso a cada range
            if found > 0:
                save_dataset(companies)

    save_dataset(companies)
    elapsed = time.time() - t0

    print(f"\n\n{'=' * 60}")
    print(f"  Concluído em {elapsed:.0f}s")
    print(f"  Total empresas: {len(companies)}")
    print(f"  Arquivo: {SEED_FILE.absolute()}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
