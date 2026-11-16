from datetime import date, datetime, time, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AvailabilityRuleInput(BaseModel):
    weekday: int = Field(ge=0, le=6, description="Monday is 0 and Sunday is 6")
    local_start: time
    local_end: time
    session_duration_minutes: int = Field(gt=0, le=1440)
    price_minor: int = Field(ge=0, le=2_147_483_647)
    currency: str = "UAH"
    valid_from: date
    valid_until: date | None = None

    @field_validator("local_start", "local_end")
    @classmethod
    def require_local_wall_time(cls, value: time) -> time:
        if value.tzinfo is not None:
            raise ValueError("Availability rule times must be local wall-clock times")
        if value.second or value.microsecond:
            raise ValueError("Availability rule times must have minute precision")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        normalized = value.upper()
        if normalized != "UAH":
            raise ValueError("Only UAH is supported for this milestone")
        return normalized

    @model_validator(mode="after")
    def validate_rule_range(self) -> "AvailabilityRuleInput":
        if self.local_end <= self.local_start:
            raise ValueError("local_end must be later than local_start on the same weekday")
        window_minutes = int(
            (
                datetime.combine(date.min, self.local_end)
                - datetime.combine(date.min, self.local_start)
            )
            / timedelta(minutes=1)
        )
        if self.session_duration_minutes > window_minutes:
            raise ValueError("session_duration_minutes must fit inside the availability window")
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("valid_until must not precede valid_from")
        first_weekday = self.valid_from + timedelta(
            days=(self.weekday - self.valid_from.weekday()) % 7
        )
        if self.valid_until is not None and first_weekday > self.valid_until:
            raise ValueError("The date range contains no occurrence of the selected weekday")
        return self


class AvailabilityRuleUpdate(AvailabilityRuleInput):
    pass


class AvailabilityRuleRead(AvailabilityRuleInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    psychologist_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AvailabilitySlotRead(BaseModel):
    id: UUID
    starts_at: datetime
    ends_at: datetime
    price_minor: int
    currency: str
    state: Literal["available"] = "available"


class PublicAvailabilityRead(BaseModel):
    psychologist_id: str
    time_zone: str
    slots: list[AvailabilitySlotRead]


class PublicPsychologistRead(BaseModel):
    public_id: str
    display_name: str
    time_zone: str
    session_duration_minutes: int | None
    price_minor: int | None
    currency: str | None
