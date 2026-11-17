from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class VerificationRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    psychologist_public_id: str = Field(min_length=8, max_length=32)

    @field_validator("email")
    @classmethod
    def valid_email_shape(cls, value: str) -> str:
        value = value.strip()
        if value.count("@") != 1 or any(character.isspace() for character in value):
            raise ValueError("Enter a valid email address")
        local, domain = value.rsplit("@", 1)
        if (
            not local
            or len(local) > 64
            or len(domain) > 255
            or "." not in domain
            or domain.startswith(".")
            or domain.endswith(".")
        ):
            raise ValueError("Enter a valid email address")
        return f"{local.lower()}@{domain.lower()}"


class VerificationConsumeRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class VerificationAccepted(BaseModel):
    status: str = "accepted"


class VerificationGrantRead(BaseModel):
    status: str = "verified"
    booking_verification_token: str
    expires_at: datetime
    psychologist_public_id: str
