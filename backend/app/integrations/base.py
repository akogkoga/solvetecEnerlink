"""Classe base para todos os adaptadores de APIs externas."""
import httpx
import asyncio
import time
import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from app.models.schemas import FilterRequest, LeadNormalized
from app.core.config import DEFAULT_TIMEOUT, MAX_RETRIES, RETRY_BACKOFF_FACTOR
from app.services.health_tracker import health_tracker


class BaseAPIAdapter(ABC):
    """Adaptador base com retry, timeout, rate limiting e health tracking."""

    PROVIDER_NAME: str = "Base"
    RATE_DELAY: float = 1.0

    def __init__(self):
        self.logger = logging.getLogger(f"provider.{self.PROVIDER_NAME}")
        self._last_request_time: float = 0

    @abstractmethod
    async def fetch_leads(self, filters: FilterRequest) -> List[dict]:
        """Busca leads na API externa de forma assíncrona."""
        pass

    @abstractmethod
    def normalize(self, raw_data: dict) -> LeadNormalized:
        """Converte o formato da API externa para o formato padrão."""
        pass

    async def fetch_by_cnpj(self, cnpj: str) -> Optional[dict]:
        """Busca dados de uma empresa por CNPJ."""
        return None

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        timeout: int = DEFAULT_TIMEOUT,
        **kwargs,
    ) -> Optional[httpx.Response]:
        """Executa request HTTP com retry, backoff, rate limiting e tracking."""
        await self._apply_rate_limit()
        start = time.monotonic()

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.request(method, url, **kwargs)

                elapsed_ms = (time.monotonic() - start) * 1000

                if response.status_code == 429:
                    wait = RETRY_BACKOFF_FACTOR * attempt * 2
                    self.logger.warning(
                        "Rate limit (429) — aguardando %.1fs (tentativa %d/%d)",
                        wait, attempt, MAX_RETRIES,
                    )
                    await asyncio.sleep(wait)
                    continue

                if response.status_code >= 500:
                    self.logger.warning(
                        "Erro %d (tentativa %d/%d)",
                        response.status_code, attempt, MAX_RETRIES,
                    )
                    await asyncio.sleep(RETRY_BACKOFF_FACTOR * attempt)
                    continue

                if response.status_code >= 400:
                    self._update_last_request_time()
                    health_tracker.record_failure(
                        self.PROVIDER_NAME,
                        f"HTTP {response.status_code}",
                    )
                    return response

                self._update_last_request_time()
                health_tracker.record_success(
                    self.PROVIDER_NAME, elapsed_ms,
                )
                return response

            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
                self.logger.warning(
                    "Tentativa %d/%d: %s",
                    attempt, MAX_RETRIES, str(exc),
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_FACTOR * attempt)

        health_tracker.record_failure(
            self.PROVIDER_NAME, "todas as tentativas falharam",
        )
        self.logger.error("Todas as tentativas falharam")
        return None

    async def _apply_rate_limit(self) -> None:
        """Aplica delay entre requests para respeitar rate limits."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.RATE_DELAY and self._last_request_time > 0:
            wait = self.RATE_DELAY - elapsed
            self.logger.debug("Rate limit delay: %.1fs", wait)
            await asyncio.sleep(wait)

    def _update_last_request_time(self) -> None:
        """Atualiza timestamp do último request."""
        self._last_request_time = time.monotonic()
