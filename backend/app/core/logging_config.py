"""Configuração de logging com saída para console (UTF-8) e arquivo."""
import logging
import sys
import io
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "backend.log"


def setup_logging(level: str = "INFO") -> None:
    """Configura logging global com formato padronizado e log em arquivo."""
    log_format = (
        "%(asctime)s | %(levelname)-7s | %(name)-25s | %(message)s"
    )

    # Console handler com UTF-8 (evita crash no Windows cp1252)
    utf8_stream = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace",
    )
    console_handler = logging.StreamHandler(utf8_stream)

    # File handler — logs persistentes
    LOG_DIR.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[console_handler, file_handler],
        force=True,
    )

    # Reduz ruído de libs externas
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
