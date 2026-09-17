from pydantic import BaseModel, Field

PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class BillRequest(BaseModel):
    account_id: int | None = None
    kwh: float = Field(ge=0)
    peak: bool = False
    persist: bool = True
    # When set, billing runs the solar-offset pipeline for this account+period.
    period: str | None = Field(default=None, pattern=PERIOD_PATTERN)


class CompareRequest(BaseModel):
    kwh: float = Field(ge=0)
    persist: bool = False


class CalcRunOut(BaseModel):
    id: int
    kind: str
    account_id: int | None
    input_json: str
    result_json: str
    created_at: str
