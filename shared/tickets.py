from shared.models import TicketValidationResult


async def validate_ticket(ticket_number: str) -> TicketValidationResult:
    # Connectwise Ticket Format Check
    if not ticket_number.startswith("#"):
        return TicketValidationResult(
            is_valid=False,
            reason='Ticket number must start with "#".',
        )

    return TicketValidationResult(is_valid=True)
