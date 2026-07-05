from pydantic import BaseModel, Field, field_validator


class PimActivationRequest(BaseModel):
    role_name: str = Field(alias="roleName", min_length=1)
    duration_hours: int = Field(alias="durationHours", ge=1, le=24)
    ticket_number: str = Field(alias="ticketNumber", min_length=3)
    justification: str | None = None

    @field_validator("ticket_number")
    @classmethod
    def normalize_ticket_number(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("role_name")
    @classmethod
    def normalize_role_name(cls, value: str) -> str:
        return value.strip()


class TicketValidationResult(BaseModel):
    is_valid: bool
    reason: str | None = None
