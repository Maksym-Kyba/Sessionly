from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PsychologistProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=200)
    time_zone: str | None = Field(default=None, max_length=64)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("display_name cannot be null")
        normalized = value.strip()
        if not normalized:
            raise ValueError("display_name cannot be blank")
        if len(normalized) > 200:
            raise ValueError("display_name must be at most 200 characters")
        return normalized

    @field_validator("time_zone")
    @classmethod
    def validate_time_zone(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("time_zone cannot be null")
        normalized = value.strip()
        if not normalized:
            raise ValueError("time_zone cannot be blank")
        try:
            ZoneInfo(normalized)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("time_zone must be a valid IANA time zone") from exc
        return normalized


class PsychologistMeRead(BaseModel):
    public_id: str
    display_name: str
    email: str | None
    time_zone: str
    csrf_token: str
