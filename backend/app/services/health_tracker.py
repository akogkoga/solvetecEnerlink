"""Rastreamento de saúde dos providers de dados empresariais."""
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger("service.health_tracker")


@dataclass
class ProviderHealth:
    """Métricas de saúde de um provider individual."""

    name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_response_time_ms: float = 0
    last_status: str = "unknown"
    last_error: Optional[str] = None
    last_request_epoch: Optional[float] = None

    @property
    def success_rate(self) -> float:
        """Taxa de sucesso em porcentagem."""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests * 100

    @property
    def avg_response_time_ms(self) -> float:
        """Tempo médio de resposta em milissegundos."""
        if self.successful_requests == 0:
            return 0.0
        return self.total_response_time_ms / self.successful_requests

    def record_success(self, response_time_ms: float) -> None:
        """Registra uma chamada bem-sucedida."""
        self.total_requests += 1
        self.successful_requests += 1
        self.total_response_time_ms += response_time_ms
        self.last_status = "online"
        self.last_error = None
        self.last_request_epoch = time.time()

    def record_failure(self, error: str) -> None:
        """Registra uma chamada que falhou."""
        self.total_requests += 1
        self.failed_requests += 1
        self.last_status = "offline"
        self.last_error = error
        self.last_request_epoch = time.time()

    def to_dict(self) -> dict:
        """Serializa métricas para JSON."""
        return {
            "name": self.name,
            "status": self.last_status,
            "total_requests": self.total_requests,
            "success_rate": round(self.success_rate, 1),
            "avg_response_time_ms": round(self.avg_response_time_ms),
            "last_error": self.last_error,
            "last_request_epoch": self.last_request_epoch,
        }


class HealthTracker:
    """Rastreador global de saúde de todos os providers."""

    def __init__(self):
        self._providers: Dict[str, ProviderHealth] = {}

    def get_or_create(self, provider_name: str) -> ProviderHealth:
        """Retorna ou cria registro de saúde para um provider."""
        if provider_name not in self._providers:
            self._providers[provider_name] = ProviderHealth(name=provider_name)
        return self._providers[provider_name]

    def record_success(self, name: str, response_time_ms: float) -> None:
        """Registra sucesso com tempo de resposta."""
        health = self.get_or_create(name)
        health.record_success(response_time_ms)
        logger.info(
            "%s: sucesso em %.0fms (taxa: %.1f%%)",
            name, response_time_ms, health.success_rate,
        )

    def record_failure(self, name: str, error: str) -> None:
        """Registra falha com mensagem de erro."""
        health = self.get_or_create(name)
        health.record_failure(error)
        logger.warning(
            "%s: falha — %s (taxa: %.1f%%)",
            name, error, health.success_rate,
        )

    def get_all_status(self) -> list:
        """Retorna status de todos os providers rastreados."""
        return [h.to_dict() for h in self._providers.values()]

    def is_healthy(self, name: str) -> bool:
        """Verifica se provider está saudável (>30% sucesso)."""
        health = self.get_or_create(name)
        if health.total_requests < 5:
            return True
        recent_age = time.time() - health.last_request_epoch if health.last_request_epoch else 0
        if health.success_rate == 0 and recent_age < 60:
            return False
        return health.success_rate >= 20.0


# Instância global — compartilhada durante o ciclo de vida da aplicação
health_tracker = HealthTracker()
