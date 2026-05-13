"""API endpoints for the B2B lead engine."""
import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import FilterRequest, LeadResponse
from app.services.health_tracker import health_tracker
from app.services.lead_generator import LeadGeneratorService
from app.services.provider_manager import ProviderManager

logger = logging.getLogger("api.endpoints")
router = APIRouter()


@router.post("/leads/generate", response_model=LeadResponse)
async def generate_leads(filters: FilterRequest):
    """Generate real leads using local discovery, fallback and enrichment."""
    try:
        logger.info(
            "Request: term=%s cnae=%s uf=%s city=%s page=%s qty=%s",
            filters.termo,
            filters.cnae,
            filters.estado,
            filters.cidade,
            filters.pagina,
            filters.quantidade,
        )
        service = LeadGeneratorService()
        result = await service.generate(filters)
        logger.info(
            "Response: %d leads in %dms providers=%s",
            result.total_returned,
            result.search_time_ms,
            ",".join(result.providers_used),
        )
        return result
    except Exception as exc:
        logger.exception("Lead generation failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/providers/status")
async def providers_status():
    """Return configured provider status."""
    manager = ProviderManager()
    return manager.get_status()


@router.get("/providers/health")
async def providers_health():
    """Return tracked provider health metrics."""
    return {
        "providers": health_tracker.get_all_status(),
        "summary": {
            "total_tracked": len(health_tracker.get_all_status()),
        },
    }
