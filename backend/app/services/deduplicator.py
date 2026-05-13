from typing import List
from app.models.schemas import LeadNormalized

class DeduplicatorService:
    @staticmethod
    def remove_duplicates(leads: List[LeadNormalized]) -> List[LeadNormalized]:
        """Remove leads com o mesmo CNPJ."""
        seen_cnpjs = set()
        unique_leads = []
        for lead in leads:
            if not lead.cnpj:
                continue
            if lead.cnpj not in seen_cnpjs:
                seen_cnpjs.add(lead.cnpj)
                unique_leads.append(lead)
        return unique_leads
