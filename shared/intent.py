import re
import json

import httpx

from shared.config import settings
from shared.models import PimActivationRequest


async def extract_pim_intent(message: str) -> PimActivationRequest:
    if settings.foundry_intent_mode == "foundry":
        return await extract_pim_intent_with_foundry(message)

    return extract_pim_intent_locally(message)


def extract_pim_intent_locally(message: str) -> PimActivationRequest:
    role_name = next(
        (
            role
            for role in settings.allowed_role_names()
            if role.lower() in message.lower()
        ),
        None,
    )
    duration_match = re.search(r"(\d+)\s*(?:hour|hours|hr|hrs)\b", message, re.IGNORECASE)
    ticket_match = re.search(r"\bTicket[\w-]+\b", message, re.IGNORECASE)

    missing = []
    if not role_name:
        missing.append("roleName")
    if not duration_match:
        missing.append("durationHours")
    if not ticket_match:
        missing.append("ticketNumber")

    if missing:
        raise ValueError(f"Missing required information: {', '.join(missing)}")

    ticket_number = ticket_match.group(0)
    return PimActivationRequest.model_validate(
        {
            "roleName": role_name,
            "durationHours": int(duration_match.group(1)),
            "ticketNumber": ticket_number,
            "justification": ticket_number,
        }
    )


async def extract_pim_intent_with_foundry(message: str) -> PimActivationRequest:
    if not settings.foundry_responses_endpoint:
        raise RuntimeError("Missing required setting: FOUNDRY_RESPONSES_ENDPOINT")

    access_token = get_foundry_access_token()
    payload = {
        "input": [
            {
                "role": "system",
                "content": (
                    "Extract Microsoft Entra PIM activation intent. Return only JSON with "
                    "roleName, durationHours, ticketNumber, and justification. Supported roles: "
                    f"{', '.join(settings.allowed_role_names())}. durationHours must be 1 to "
                    f"{settings.max_pim_duration_hours}. ticketNumber must start with Ticket. "
                    "If justification is missing, use ticketNumber. Do not activate PIM."
                ),
            },
            {
                "role": "user",
                "content": message,
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "pim_activation_intent",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["roleName", "durationHours", "ticketNumber", "justification"],
                    "properties": {
                        "roleName": {
                            "type": "string",
                            "enum": settings.allowed_role_names(),
                        },
                        "durationHours": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": settings.max_pim_duration_hours,
                        },
                        "ticketNumber": {
                            "type": "string",
                            "pattern": "^Ticket",
                        },
                        "justification": {
                            "type": "string",
                        },
                    },
                },
            }
        },
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            settings.foundry_responses_endpoint,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    response.raise_for_status()
    intent_payload = extract_json_from_foundry_response(response.json())
    return PimActivationRequest.model_validate(intent_payload)


def get_foundry_access_token() -> str:
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

    if settings.foundry_managed_identity_client_id:
        credential = ManagedIdentityCredential(
            client_id=settings.foundry_managed_identity_client_id
        )
    else:
        credential = DefaultAzureCredential()

    return credential.get_token(settings.foundry_token_scope).token


def extract_json_from_foundry_response(response_body: dict) -> dict:
    if response_body.get("output_text"):
        return json.loads(response_body["output_text"])

    for output_item in response_body.get("output", []):
        for content_item in output_item.get("content", []):
            if content_item.get("type") in {"output_text", "text"}:
                text = content_item.get("text")
                if text:
                    return json.loads(text)

    raise RuntimeError("Foundry response did not contain JSON output.")
