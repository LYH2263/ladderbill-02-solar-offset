from pydantic import BaseModel, Field

PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class SolarOffsetCreate(BaseModel):
    # account_id comes from the URL path.
    period: str = Field(pattern=PERIOD_PATTERN)
    offset_kwh: float = Field(ge=0)
    source_note: str | None = None
    entered_by: str | None = None


class SolarOffsetCorrect(BaseModel):
    # Explicit expected version of the record being corrected; rejected on mismatch.
    base_version: int = Field(ge=1)
    offset_kwh: float = Field(ge=0)
    source_note: str | None = None
    entered_by: str | None = None


class SolarOffsetVoid(BaseModel):
    # Explicit expected version guards against voiding a record you didn't see.
    base_version: int = Field(ge=1)


class SolarPreviewRequest(BaseModel):
    account_id: int
    period: str = Field(pattern=PERIOD_PATTERN)
    gross_kwh: float = Field(ge=0)
    peak: bool = False


class SolarOffsetOut(BaseModel):
    id: int
    account_id: int
    period: str
    version: int
    offset_kwh: float
    source_note: str | None = None
    entered_by: str | None = None
    is_active: int
    supersedes_id: int | None = None
    created_at: str
