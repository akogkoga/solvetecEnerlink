"""Cache híbrido — Redis quando disponível, memória como fallback."""
import time
import hashlib
import json
import logging
from typing import Optional, Any
from app.models.schemas import LeadResponse
from app.core.config import (
    CACHE_TTL_SECONDS, CACHE_MAX_ENTRIES, REDIS_URL, REDIS_ENABLED,
)

logger = logging.getLogger("service.cache")


class MemoryCache:
    """Cache em memória com TTL — usado como fallback quando Redis indisponível."""

    def __init__(self):
        self._store: dict[str, dict] = {}

    def get(self, key: str) -> Optional[Any]:
        """Retorna valor do cache se existir e não estiver expirado."""
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry["timestamp"] > CACHE_TTL_SECONDS:
            del self._store[key]
            return None
        logger.info("Cache HIT (memória) — chave %s", key[:16])
        return entry["value"]

    def set(self, key: str, value: Any) -> None:
        """Armazena valor no cache com timestamp atual."""
        if len(self._store) >= CACHE_MAX_ENTRIES:
            self._evict_oldest()
        self._store[key] = {
            "value": value,
            "timestamp": time.monotonic(),
        }

    def clear(self) -> None:
        """Limpa todo o cache."""
        self._store.clear()

    @property
    def size(self) -> int:
        """Retorna número de entradas no cache."""
        return len(self._store)

    def _evict_oldest(self) -> None:
        """Remove a entrada mais antiga do cache."""
        if not self._store:
            return
        oldest = min(self._store, key=lambda k: self._store[k]["timestamp"])
        del self._store[oldest]


class RedisCache:
    """Cache Redis com serialização JSON e TTL nativo."""

    def __init__(self, url: str):
        import redis
        self._client = redis.from_url(url, decode_responses=True)
        self._prefix = "enerlink:"

    def get(self, key: str) -> Optional[Any]:
        """Busca valor no Redis e desserializa JSON."""
        raw = self._client.get(f"{self._prefix}{key}")
        if raw is None:
            return None
        logger.info("Cache HIT (Redis) — chave %s", key[:16])
        return LeadResponse.model_validate(json.loads(raw))

    def set(self, key: str, value: Any) -> None:
        """Armazena valor serializado no Redis com TTL."""
        serialized = json.dumps(value, default=_serialize_pydantic)
        self._client.setex(
            f"{self._prefix}{key}", CACHE_TTL_SECONDS, serialized,
        )

    def clear(self) -> None:
        """Remove todas as chaves do namespace enerlink."""
        keys = self._client.keys(f"{self._prefix}*")
        if keys:
            self._client.delete(*keys)

    @property
    def size(self) -> int:
        """Conta entradas no namespace."""
        return len(self._client.keys(f"{self._prefix}*"))


def _serialize_pydantic(obj: Any) -> Any:
    """Serializa objetos Pydantic para JSON."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _build_cache() -> MemoryCache | RedisCache:
    """Constrói instância de cache baseado na configuração."""
    if REDIS_ENABLED:
        try:
            cache = RedisCache(REDIS_URL)
            cache._client.ping()
            logger.info("Cache Redis conectado: %s", REDIS_URL)
            return cache
        except Exception as exc:
            logger.warning(
                "Redis indisponível (%s) — usando cache em memória", str(exc),
            )
    return MemoryCache()


class CacheService:
    """Facade do cache com método utilitário para gerar chaves."""

    @staticmethod
    def make_key(filters_dict: dict) -> str:
        """Gera chave de cache baseada no hash dos filtros."""
        serialized = json.dumps(filters_dict, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()


# Instância global — Redis se configurado, memória como fallback
cache_instance = _build_cache()
