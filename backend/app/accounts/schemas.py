from pydantic import BaseModel


class PsychologistMeRead(BaseModel):
    public_id: str
    display_name: str
    email: str | None
    time_zone: str
    csrf_token: str
