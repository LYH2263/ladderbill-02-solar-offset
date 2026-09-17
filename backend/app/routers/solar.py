from fastapi import APIRouter

from app.schemas.solar import (
    SolarOffsetCorrect,
    SolarOffsetCreate,
    SolarOffsetVoid,
    SolarPreviewRequest,
)
from app.services.billing_service import BillingService

router = APIRouter(tags=["solar-offset"])


@router.get("/accounts/{account_id}/solar-offsets")
def list_offsets(account_id: int):
    with BillingService() as svc:
        return {"items": svc.list_offsets(account_id)}


@router.post("/accounts/{account_id}/solar-offsets", status_code=201)
def create_offset(account_id: int, body: SolarOffsetCreate):
    with BillingService() as svc:
        return svc.create_offset(
            account_id=account_id,
            period=body.period,
            offset_kwh=body.offset_kwh,
            source_note=body.source_note,
            entered_by=body.entered_by,
        )


@router.post("/accounts/{account_id}/solar-offsets/{period}/correct")
def correct_offset(account_id: int, period: str, body: SolarOffsetCorrect):
    with BillingService() as svc:
        return svc.correct_offset(
            account_id,
            period,
            base_version=body.base_version,
            offset_kwh=body.offset_kwh,
            source_note=body.source_note,
            entered_by=body.entered_by,
        )


@router.post("/accounts/{account_id}/solar-offsets/{period}/void")
def void_offset(account_id: int, period: str, body: SolarOffsetVoid):
    # The explicit expected version guards against voiding a record you didn't see.
    with BillingService() as svc:
        return svc.void_offset(account_id, period, body.base_version)


@router.post("/solar-offset/preview")
def preview_offset(body: SolarPreviewRequest):
    with BillingService() as svc:
        return svc.preview_offset_bill(
            account_id=body.account_id,
            period=body.period,
            gross_kwh=body.gross_kwh,
            peak=body.peak,
        )
