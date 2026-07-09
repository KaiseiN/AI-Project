import asyncio
import json
import logging
import re

import httpx
from pydantic import ValidationError

from shared.config import settings
from shared.models import PimActivationRequest


class IntentClarificationRequired(ValueError):
    def __init__(
        self,
        missing_fields: list[str],
        partial_payload: dict,
        message: str | None = None,
    ) -> None:
        self.missing_fields = missing_fields
        self.partial_payload = partial_payload
        self.clarification_message = message
        super().__init__(message or f"Missing required information: {', '.join(missing_fields)}")


async def extract_pim_intent(message: str) -> PimActivationRequest:
    if settings.foundry_intent_mode == "foundry":
        try:
            return await extract_pim_intent_with_foundry(message)
        except IntentClarificationRequired:
            raise
        except Exception:
            logging.exception("Foundry intent extraction failed; falling back to local extraction")
            return extract_pim_intent_locally(message)

    return extract_pim_intent_locally(message)


def extract_pim_intent_locally(message: str) -> PimActivationRequest:
    partial_payload = extract_local_intent_fields(message)
    missing = missing_required_intent_fields(partial_payload)

    if missing:
        raise IntentClarificationRequired(missing, partial_payload)

    return PimActivationRequest.model_validate(partial_payload)


def extract_local_intent_fields(message: str) -> dict:
    role_name = next(
        (
            role
            for role in settings.allowed_role_names()
            if role.lower() in message.lower()
        ),
        None,
    )
    duration_match = re.search(r"(\d+)\s*(?:hour|hours|hr|hrs)\b", message, re.IGNORECASE)
    ticket_match = re.search(r"#[A-Za-z0-9][\w-]*", message)

    partial_payload = {}
    if role_name:
        partial_payload["roleName"] = role_name

    if duration_match:
        partial_payload["durationHours"] = int(duration_match.group(1))

    if ticket_match:
        partial_payload["ticketNumber"] = ticket_match.group(0)
        partial_payload["justification"] = ticket_match.group(0)

    return partial_payload


async def extract_pim_intent_with_foundry(message: str) -> PimActivationRequest:
    if settings.foundry_project_endpoint:
        return await asyncio.to_thread(extract_pim_intent_with_foundry_sdk, message)

    if not settings.foundry_responses_endpoint:
        raise RuntimeError(
            "Missing required setting: FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_RESPONSES_ENDPOINT"
        )

    access_token = get_foundry_access_token()
    payload = {
        "input": foundry_input(message),
        "text": foundry_text_format(),
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            foundry_responses_url(),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    response.raise_for_status()
    intent_payload = merge_local_intent_fields(
        extract_json_from_foundry_response(response.json()),
        message,
    )
    return validate_intent_payload(intent_payload)


def extract_pim_intent_with_foundry_sdk(message: str) -> PimActivationRequest:
    from azure.ai.projects import AIProjectClient

    credential = get_foundry_credential()

    with (
        credential,
        AIProjectClient(
            endpoint=settings.foundry_project_endpoint,
            credential=credential,
            allow_preview=True,
        ) as project_client,
    ):
        if not settings.foundry_agent_version:
            raise RuntimeError("Missing required setting: FOUNDRY_AGENT_VERSION")

        openai_client = project_client.get_openai_client()
        response = openai_client.responses.create(
            input=[{"role": "user", "content": foundry_agent_input(message)}],
            extra_body={
                "agent_reference": {
                    "name": settings.foundry_agent_name,
                    "version": settings.foundry_agent_version,
                    "type": "agent_reference",
                }
            },
        )

    intent_payload = merge_local_intent_fields(
        extract_json_from_foundry_response(response.model_dump()),
        message,
    )
    return validate_intent_payload(intent_payload)


def merge_local_intent_fields(intent_payload: dict, message: str) -> dict:
    local_payload = extract_local_intent_fields(message)
    merged_payload = dict(intent_payload)

    if isinstance(merged_payload.get("partialPayload"), dict):
        merged_payload["partialPayload"] = {
            **partial_intent_payload(merged_payload["partialPayload"]),
            **local_payload,
        }

    for field_name, value in local_payload.items():
        if not merged_payload.get(field_name) or field_name in {"ticketNumber", "justification"}:
            merged_payload[field_name] = value

    missing_fields = missing_required_intent_fields(merged_payload)
    if not missing_fields and merged_payload.get("status") == "needs_input":
        merged_payload.pop("status", None)
        merged_payload.pop("message", None)
        merged_payload.pop("missingFields", None)
        merged_payload.pop("partialPayload", None)

    return merged_payload


def validate_intent_payload(intent_payload: dict) -> PimActivationRequest:
    missing_fields = intent_payload.get("missingFields") or missing_required_intent_fields(
        intent_payload
    )
    if intent_payload.get("status") == "needs_input" or missing_fields:
        raise IntentClarificationRequired(
            missing_fields,
            intent_payload.get("partialPayload") or partial_intent_payload(intent_payload),
            intent_payload.get("message"),
        )

    try:
        return PimActivationRequest.model_validate(intent_payload)
    except ValidationError as exc:
        missing_fields = [
            ".".join(str(part) for part in error["loc"])
            for error in exc.errors()
            if error["type"] == "missing"
        ]
        if missing_fields:
            raise IntentClarificationRequired(missing_fields, intent_payload) from exc

        raise


def missing_required_intent_fields(intent_payload: dict) -> list[str]:
    missing_fields = []
    for field_name in ("roleName", "durationHours", "ticketNumber"):
        value = intent_payload.get(field_name)
        if value is None:
            missing_fields.append(field_name)
        elif isinstance(value, str) and not value.strip():
            missing_fields.append(field_name)

    return missing_fields


def partial_intent_payload(intent_payload: dict) -> dict:
    return {
        field_name: value
        for field_name, value in intent_payload.items()
        if field_name in {"roleName", "durationHours", "ticketNumber", "justification"}
        and value is not None
        and not (isinstance(value, str) and not value.strip())
    }


def foundry_agent_input(message: str) -> str:
    return (
        "Follow your configured PIM activation intent-extraction instructions.\n"
        "Return only valid JSON with no markdown.\n"
        "If all required fields are present, return roleName, durationHours, "
        "ticketNumber, and justification.\n"
        "If required fields are missing, return status='needs_input', message, "
        "missingFields, and partialPayload.\n"
        'ticketNumber must start with "#", for example "#12345".\n'
        'If the user provides a ticket number without "#", ask them to provide it with "#".\n'
        "Do not activate PIM.\n\n"
        f"User request: {message}"
    )


def foundry_input(message: str) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "Extract Microsoft Entra PIM activation intent. Return only JSON with "
                "roleName, durationHours, ticketNumber, and justification. Supported roles: "
                f"{', '.join(settings.allowed_role_names())}. durationHours must be 1 to "
                f'{settings.max_pim_duration_hours}. ticketNumber must start with "#". '
                "If justification is missing, use ticketNumber. Do not activate PIM."
            ),
        },
        {
            "role": "user",
            "content": message,
        },
    ]


def foundry_text_format() -> dict:
    return {
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
                        "pattern": "^#",
                    },
                    "justification": {
                        "type": "string",
                    },
                },
            },
        }
    }


def foundry_responses_url() -> httpx.URL:
    url = httpx.URL(settings.foundry_responses_endpoint)
    query_params = dict(url.params.multi_items())
    if "api-version" in query_params:
        return url

    return url.copy_add_param("api-version", settings.foundry_api_version)


def get_foundry_credential():
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

    if settings.foundry_managed_identity_client_id:
        return ManagedIdentityCredential(
            client_id=settings.foundry_managed_identity_client_id
        )

    return DefaultAzureCredential()


def get_foundry_access_token() -> str:
    credential = get_foundry_credential()
    return credential.get_token(settings.foundry_token_scope).token


def extract_json_from_foundry_response(response_body: dict) -> dict:
    if response_body.get("output_text"):
        return parse_json_object(response_body["output_text"])

    for output_item in response_body.get("output", []):
        if output_item.get("type") == "message":
            for content_item in output_item.get("content", []):
                text = extract_text_from_content_item(content_item)
                if text:
                    return parse_json_object(text)

        for content_item in output_item.get("content", []):
            text = extract_text_from_content_item(content_item)
            if text:
                return parse_json_object(text)

    preview = json.dumps(response_body)[:1000]
    raise RuntimeError(f"Foundry response did not contain JSON output. Preview: {preview}")


def extract_text_from_content_item(content_item: dict) -> str | None:
    if content_item.get("type") in {"output_text", "text"}:
        text = content_item.get("text")
        if isinstance(text, str):
            return text

    text = content_item.get("text")
    if isinstance(text, str):
        return text

    if isinstance(text, dict) and isinstance(text.get("value"), str):
        return text["value"]

    return None


def parse_json_object(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise

        return json.loads(text[start : end + 1])
