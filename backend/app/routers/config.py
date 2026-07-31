"""Public / shared config endpoints (no superadmin required to read)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.schemas_auth import FaultCategoriesOut
from backend.app.services import fault_categories as fault_cat_service

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/fault-categories", response_model=FaultCategoriesOut)
def get_fault_categories(db: Session = Depends(get_db)):
    """Results UI uses this to split Actionable vs Non-actionable fault tabs."""
    return FaultCategoriesOut(**fault_cat_service.category_payload(db))
