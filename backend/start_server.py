"""Operational backend runner with validation, logging and auto-restart."""
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
LOG_DIR = BACKEND_DIR / "logs"
LOG_FILE = LOG_DIR / "backend.log"
VENV_PYTHON = BACKEND_DIR / "venv" / "Scripts" / "python.exe"
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = os.environ.get("PORT", "8000")
MAX_RESTARTS = int(os.environ.get("MAX_RESTARTS", "50"))
RESTART_DELAY_SECONDS = int(os.environ.get("RESTART_DELAY_SECONDS", "3"))


def setup_file_logger() -> logging.Logger:
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )
    return logging.getLogger("server_runner")


def validate_environment(logger: logging.Logger) -> bool:
    errors: list[str] = []

    if not VENV_PYTHON.exists():
        errors.append(f"venv python not found: {VENV_PYTHON}")
    else:
        probe = subprocess.run(
            [str(VENV_PYTHON), "--version"],
            cwd=str(BACKEND_DIR),
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            errors.append(
                "venv python exists but does not start. Recreate it with: "
                "py -3.12 -m venv venv && .\\venv\\Scripts\\pip.exe install -r requirements.txt"
            )

    for required in ("requirements.txt", "main.py"):
        if not (BACKEND_DIR / required).exists():
            errors.append(f"{required} not found")

    if not os.environ.get("CASADOSDADOS_API_KEY", ""):
        logger.warning("CASADOSDADOS_API_KEY is not configured; Casa dos Dados discovery will be skipped")

    logger.info("Redis: %s", "enabled" if os.environ.get("REDIS_ENABLED", "false").lower() == "true" else "disabled")

    if errors:
        for err in errors:
            logger.error("VALIDATION FAILED: %s", err)
        return False

    logger.info("Validation OK")
    return True


def run_server(logger: logging.Logger) -> subprocess.Popen:
    cmd = [
        str(VENV_PYTHON),
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        HOST,
        "--port",
        PORT,
        "--log-level",
        "info",
    ]
    logger.info("Starting: %s", " ".join(cmd))
    return subprocess.Popen(
        cmd,
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def stream_output(process: subprocess.Popen) -> None:
    if process.stdout is None:
        return
    for line in process.stdout:
        clean = line.rstrip()
        if clean:
            print(clean)


def main() -> None:
    logger = setup_file_logger()
    logger.info("=" * 60)
    logger.info("Motor de Leads B2B backend runner")
    logger.info("Host: %s | Port: %s | Logs: %s", HOST, PORT, LOG_FILE)
    logger.info("=" * 60)

    if not validate_environment(logger):
        sys.exit(1)

    restart_count = 0
    while restart_count < MAX_RESTARTS:
        logger.info("Starting backend attempt %d/%d", restart_count + 1, MAX_RESTARTS)
        process = run_server(logger)
        try:
            stream_output(process)
            exit_code = process.wait()
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
            process.terminate()
            process.wait(timeout=5)
            break

        if exit_code == 0:
            logger.info("Backend exited normally")
            break

        restart_count += 1
        logger.warning("Backend crashed with exit %d; restarting in %ds", exit_code, RESTART_DELAY_SECONDS)
        time.sleep(RESTART_DELAY_SECONDS)

    if restart_count >= MAX_RESTARTS:
        logger.error("Restart limit reached: %d", MAX_RESTARTS)


if __name__ == "__main__":
    main()
