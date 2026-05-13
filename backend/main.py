"""Motor de Leads B2B — Ponto de entrada FastAPI."""
import time
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import router as api_router
from app.core.logging_config import setup_logging
from app.services.health_tracker import health_tracker

setup_logging()
logger = logging.getLogger("main")

START_TIME = time.time()

app = FastAPI(
    title="Motor de Geração de Leads B2B",
    description="SaaS Backend para busca e qualificação de empresas",
    version="1.0.0",
)

# CORS — permite frontend em qualquer porta local e file://
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5501",
        "http://127.0.0.1:5501",
        "http://localhost:8000",
        "null",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def read_root():
    """Mensagem de status do servidor."""
    return {"message": "Motor de Leads B2B Ativo e Rodando."}


@app.get("/health")
def health_check():
    """Health check detalhado para validação de disponibilidade."""
    uptime_sec = int(time.time() - START_TIME)
    hours = uptime_sec // 3600
    minutes = (uptime_sec % 3600) // 60
    seconds = uptime_sec % 60

    providers = health_tracker.get_all_status()
    cache_type, cache_size = _detect_cache_info()

    return {
        "status": "online",
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "uptime_seconds": uptime_sec,
        "providers": providers,
        "cache": {
            "type": cache_type,
            "size": cache_size,
        },
    }


def _detect_cache_info() -> tuple[str, int]:
    """Detecta tipo e tamanho do cache ativo."""
    from app.services.cache import cache_instance
    return type(cache_instance).__name__, getattr(cache_instance, "size", 0)


@app.on_event("startup")
async def startup_log():
    """Loga informações de inicialização."""
    logger.info("Backend iniciado — http://localhost:8000")
    logger.info("Swagger UI — http://localhost:8000/docs")
    logger.info("Health check — http://localhost:8000/health")
