"""Configurações centralizadas do sistema de geração de leads."""
import os


# --- Timeouts (segundos) ---
DEFAULT_TIMEOUT = int(os.environ.get("DEFAULT_TIMEOUT", "15"))
ENRICHMENT_TIMEOUT = int(os.environ.get("ENRICHMENT_TIMEOUT", "10"))

# --- Retry ---
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "2"))
RETRY_BACKOFF_FACTOR = float(os.environ.get("RETRY_BACKOFF_FACTOR", "1.0"))

# --- Cache ---
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "1800"))
CACHE_MAX_ENTRIES = int(os.environ.get("CACHE_MAX_ENTRIES", "500"))

# --- Redis (opcional — fallback para cache em memória) ---
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_ENABLED = os.environ.get("REDIS_ENABLED", "false").lower() == "true"

# --- Provider URLs ---
CASADOSDADOS_URL = os.environ.get(
    "CASADOSDADOS_URL",
    "https://api.casadosdados.com.br/v5/cnpj/pesquisa"
)
CASADOSDADOS_API_KEY = os.environ.get("CASADOSDADOS_API_KEY", "")
BRASILAPI_URL = os.environ.get(
    "BRASILAPI_URL",
    "https://brasilapi.com.br/api/cnpj/v1"
)
RECEITAWS_URL = os.environ.get(
    "RECEITAWS_URL",
    "https://receitaws.com.br/v1/cnpj"
)
CNPJA_URL = os.environ.get(
    "CNPJA_URL",
    "https://open.cnpja.com/office"
)
CNPJWS_URL = os.environ.get(
    "CNPJWS_URL",
    "https://publica.cnpj.ws/cnpj"
)

# --- Rate Limits (segundos entre requests) ---
RECEITAWS_RATE_DELAY = float(os.environ.get("RECEITAWS_RATE_DELAY", "20.0"))
CNPJA_RATE_DELAY = float(os.environ.get("CNPJA_RATE_DELAY", "12.0"))
CNPJWS_RATE_DELAY = float(os.environ.get("CNPJWS_RATE_DELAY", "5.0"))
BRASILAPI_RATE_DELAY = float(os.environ.get("BRASILAPI_RATE_DELAY", "1.0"))

# --- Limites ---
MAX_ENRICHMENT_CONCURRENT = int(
    os.environ.get("MAX_ENRICHMENT_CONCURRENT", "3")
)
MAX_ENRICHMENT_LEADS = int(os.environ.get("MAX_ENRICHMENT_LEADS", "6"))
ENRICHMENT_MODE = os.environ.get("ENRICHMENT_MODE", "balanced").lower()

# --- Cloudscraper ---
USE_CLOUDSCRAPER = os.environ.get(
    "USE_CLOUDSCRAPER", "true"
).lower() == "true"
