"""Registro central de providers com tipo, prioridade e health."""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from app.integrations.base import BaseAPIAdapter
from app.services.health_tracker import health_tracker

logger = logging.getLogger("service.registry")


class ProviderType(str, Enum):
    """Tipo de provider no sistema."""

    DISCOVERY = "discovery"
    ENRICHMENT = "enrichment"


@dataclass
class ProviderInfo:
    """Metadados de um provider registrado."""

    name: str
    provider_type: ProviderType
    priority: int
    adapter: BaseAPIAdapter
    description: str = ""
    requires_key: bool = False

    @property
    def is_healthy(self) -> bool:
        """Verifica saúde baseada no health tracker."""
        return health_tracker.is_healthy(self.name)

    def to_dict(self) -> dict:
        """Serializa para JSON."""
        health = health_tracker.get_or_create(self.name)
        return {
            "name": self.name,
            "type": self.provider_type.value,
            "priority": self.priority,
            "description": self.description,
            "requires_key": self.requires_key,
            "healthy": self.is_healthy,
            "status": health.last_status,
            "success_rate": round(health.success_rate, 1),
            "avg_response_ms": round(health.avg_response_time_ms),
        }


class ProviderRegistry:
    """Registro central de todos os providers do sistema."""

    def __init__(self):
        self._providers: List[ProviderInfo] = []

    def register(self, info: ProviderInfo) -> None:
        """Registra um provider no sistema."""
        self._providers.append(info)
        logger.info(
            "Registrado: %s (%s) prioridade=%d",
            info.name, info.provider_type.value, info.priority,
        )

    def get_discovery_providers(self) -> List[ProviderInfo]:
        """Retorna providers de discovery ordenados por prioridade."""
        providers = [
            p for p in self._providers
            if p.provider_type == ProviderType.DISCOVERY
        ]
        return sorted(providers, key=lambda p: p.priority)

    def get_enrichment_providers(self) -> List[ProviderInfo]:
        """Retorna providers de enrichment ordenados por prioridade."""
        providers = [
            p for p in self._providers
            if p.provider_type == ProviderType.ENRICHMENT
        ]
        return sorted(providers, key=lambda p: p.priority)

    def get_all(self) -> List[ProviderInfo]:
        """Retorna todos os providers registrados."""
        return sorted(self._providers, key=lambda p: p.priority)

    def get_status(self) -> list:
        """Retorna status de todos os providers."""
        return [p.to_dict() for p in self.get_all()]
