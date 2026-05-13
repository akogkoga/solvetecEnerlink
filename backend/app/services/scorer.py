"""Lead quality scoring."""
import logging
from typing import List

from app.models.schemas import LeadNormalized

logger = logging.getLogger("service.scorer")

WEIGHT_PHONE = 22
WEIGHT_EMAIL = 18
WEIGHT_WEBSITE = 10
WEIGHT_ACTIVE = 25
WEIGHT_COMPLETENESS = 20
WEIGHT_SOURCE = 5


class ScorerService:
    """Calculates a demo-friendly quality score from 0 to 100."""

    @staticmethod
    def calculate(lead: LeadNormalized) -> int:
        score = 0

        phone_digits = "".join(ch for ch in (lead.telefone or "") if ch.isdigit())
        if len(phone_digits) >= 8:
            score += WEIGHT_PHONE
        elif "*" in (lead.telefone or "") and len(phone_digits) >= 4:
            score += WEIGHT_PHONE - 6

        if lead.email and "@" in lead.email and "." in lead.email:
            score += WEIGHT_EMAIL
        elif "*" in (lead.email or "") and "." in lead.email:
            score += WEIGHT_EMAIL - 6

        if lead.site and len(lead.site) > 4:
            score += WEIGHT_WEBSITE

        situacao_upper = (lead.situacao or "").upper()
        if situacao_upper in ("ATIVA", "02") or "ATIVA" in situacao_upper:
            score += WEIGHT_ACTIVE

        completeness = sum([
            bool(lead.empresa),
            bool(lead.cnpj) and len(lead.cnpj) >= 14,
            bool(lead.cidade),
            bool(lead.estado),
            bool(lead.cnae),
            bool(lead.porte),
        ])
        if completeness >= 5:
            score += WEIGHT_COMPLETENESS
        elif completeness >= 3:
            score += WEIGHT_COMPLETENESS // 2

        if lead.fonte:
            score += WEIGHT_SOURCE

        return min(score, 100)

    @staticmethod
    def apply_scores(leads: List[LeadNormalized]) -> List[LeadNormalized]:
        for lead in leads:
            lead.score = ScorerService.calculate(lead)

        leads.sort(key=lambda x: x.score, reverse=True)

        if leads:
            scores = [lead.score for lead in leads]
            logger.info(
                "Scores: min=%d max=%d avg=%.0f",
                min(scores), max(scores), sum(scores) / len(scores),
            )
        return leads
