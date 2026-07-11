import json
import logging
from pathlib import Path

import azure.functions as func
import httpx
from pydantic import ValidationError

from shared.auth import acquire_graph_token_on_behalf_of, get_bearer_token
from shared.config import settings
from shared.graph import activate_pim_role, get_current_user, get_current_user_eligibilities
from shared.intent import IntentClarificationRequired, extract_pim_intent
from shared.models import IntentExtractionRequest, PimActivationRequest
from shared.responses import cors_headers, cors_preflight_response, json_response
from shared.tickets import validate_ticket

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
STATIC_ROOT = Path(__file__).parent / "orchestrator"


def get_request_json(req: func.HttpRequest) -> dict:
    try:
        return req.get_json()
    except ValueError:
        body = req.get_body().decode("utf-8")
        if not body:
            raise
        return json.loads(body)


def get_request_token(req: func.HttpRequest, payload: dict) -> str | None:
    return get_bearer_token(req) or payload.get("accessToken")


@app.route(route="orchestrator/{filename}", methods=["GET"])
async def orchestrator_static(req: func.HttpRequest) -> func.HttpResponse:
    filename = req.route_params.get("filename") or "index.html"
    if filename == "config.js":
        return func.HttpResponse(
            build_orchestrator_config(req),
            status_code=200,
            mimetype="application/javascript",
        )

    allowed_files = {
        "index.html": "text/html",
        "app.js": "application/javascript",
        "styles.css": "text/css",
    }
    mimetype = allowed_files.get(filename)
    if not mimetype:
        return func.HttpResponse("Not found", status_code=404)

    file_path = STATIC_ROOT / filename
    if not file_path.exists():
        return func.HttpResponse("Not found", status_code=404)

    return func.HttpResponse(
        file_path.read_text(encoding="utf-8"),
        status_code=200,
        mimetype=mimetype,
    )


def build_orchestrator_config(req: func.HttpRequest) -> str:
    origin = f"{req.url.split('/api/orchestrator/', 1)[0]}"
    redirect_uri = f"{origin}/api/orchestrator/index.html"
    config = {
        "tenantId": "a373f986-e6fe-48b3-8acd-d9cc4dbdb2e6",
        "clientId": "2d927dbc-e54f-4e43-a1d9-ab9988006dc6",
        "apiScope": "api://2450d4e7-7781-4a1f-885b-710a17d3d31b/pim.activate",
        "intentUrl": f"{origin}/api/intent/extract",
        "functionUrl": f"{origin}/api/pim/activate",
        "redirectUri": redirect_uri,
        "supportedRoles": ["AI Reader"],
    }
    return f"window.PIM_ORCHESTRATOR_CONFIG = {json.dumps(config, indent=2)};\n"


@app.route(route="intent/extract", methods=["POST", "OPTIONS"])
async def extract_intent(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_preflight_response()

    try:
        request_payload = get_request_json(req)
    except (ValueError, json.JSONDecodeError) as exc:
        return json_response({"error": "Invalid request", "details": str(exc)}, 400)

    bearer_token = get_request_token(req, request_payload)
    if not bearer_token:
        return json_response({"error": "Missing bearer token"}, 401)

    try:
        intent_request = IntentExtractionRequest.model_validate(request_payload)
        activation = await extract_pim_intent(intent_request.message)
    except IntentClarificationRequired as exc:
        return json_response(
            {
                "status": "needs_input",
                "message": normalize_clarification_message(
                    exc.clarification_message
                    or build_clarification_message(exc.missing_fields, exc.partial_payload)
                ),
                "missingFields": exc.missing_fields,
                "partialPayload": exc.partial_payload,
            },
            200,
        )
    except (ValueError, ValidationError) as exc:
        return json_response({"error": "Intent extraction failed", "details": str(exc)}, 400)
    except httpx.HTTPStatusError as exc:
        logging.warning("Foundry intent extraction failed: %s", exc.response.text)
        return func.HttpResponse(
            exc.response.text,
            status_code=exc.response.status_code,
            mimetype="application/json",
            headers=cors_headers(),
        )
    except Exception as exc:
        logging.exception("Intent extraction failed")
        return json_response({"error": "Intent extraction failed", "details": str(exc)}, 500)

    return json_response(
        {
            "roleName": activation.role_name,
            "durationHours": activation.duration_hours,
            "ticketNumber": activation.ticket_number,
            "justification": activation.justification,
        },
        200,
    )


def build_clarification_message(missing_fields: list[str], partial_payload: dict) -> str:
    lines = []
    if len(missing_fields) == 1:
        lines.append(f"Missing required field: {missing_fields[0]}.")
    else:
        lines.append(f"Missing required fields: {', '.join(missing_fields)}.")

    lines.extend(["", "Please reply with:"])

    if "ticketNumber" in missing_fields:
        lines.append("")
        lines.append('ticket number (must start with "#", e.g., #12345)')
        lines.append("optional justification (if omitted, I'll use the ticket number)")

    if "roleName" in missing_fields:
        lines.append("")
        lines.append(f"roleName ({', '.join(settings.allowed_role_names())})")

    if "durationHours" in missing_fields:
        lines.append("")
        lines.append(f"durationHours (1-{settings.max_pim_duration_hours})")

    if partial_payload:
        lines.extend(
            [
                "",
                "Current request details:",
                json.dumps(partial_payload, indent=2),
            ]
        )

    return "\n".join(lines)


def normalize_clarification_message(message: str) -> str:
    return (
        message.replace(
            "Missing or invalid ticketNumber. Provide a ticket number that starts with '#' "
            "(e.g., '#12345')."
        )
        .replace("ticketNumber", "ticket number")
        .replace("TicketNumber", "ticket number")
        .replace("ticketnumber", "ticket number")
        .replace("Ticket number", "ticket number")
        .replace("must start with “Ticket”", 'must start with "#"')
        .replace("must start with \"Ticket\"", 'must start with "#"')
        .replace("must start with 'Ticket'", 'must start with "#"')
        .replace("starting with 'Ticket'", 'starting with "#"')
        .replace("starting with \"Ticket\"", 'starting with "#"')
        .replace("starting with Ticket", 'starting with "#"')
        .replace("starts with “Ticket”", 'starts with "#"')
        .replace("starts with \"Ticket\"", 'starts with "#"')
        .replace("starts with 'Ticket'", 'starts with "#"')
        .replace("starts with Ticket", 'starts with "#"')
        .replace("with 'Ticket'", 'with "#"')
        .replace("with \"Ticket\"", 'with "#"')
        .replace("Ticket12345", "#12345")
        .replace("Ticket-12345", "#12345")
    )


@app.route(route="pim/activate", methods=["POST", "OPTIONS"])
async def activate_pim(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_preflight_response()

    try:
        request_payload = get_request_json(req)
        activation = PimActivationRequest.model_validate(request_payload)
    except (ValueError, ValidationError) as exc:
        return json_response({"error": "Invalid request", "details": str(exc)}, 400)

    role_definition_id = settings.role_definition_id(activation.role_name)
    if not role_definition_id:
        return json_response({"error": "Role is not allowed"}, 400)

    if activation.duration_hours > settings.max_pim_duration_hours:
        return json_response(
            {
                "error": "Duration exceeds policy",
                "maxDurationHours": settings.max_pim_duration_hours,
            },
            400,
        )

    bearer_token = get_request_token(req, request_payload)
    if not bearer_token:
        return json_response({"error": "Missing bearer token"}, 401)

    ticket_result = await validate_ticket(activation.ticket_number)
    if not ticket_result.is_valid:
        return json_response(
            {"error": "Ticket is invalid or not approved", "details": ticket_result.reason},
            400,
        )

    try:
        graph_token = acquire_graph_token_on_behalf_of(bearer_token)
        user = await get_current_user(graph_token)
        principal_id = user["id"]
        eligibilities = await get_current_user_eligibilities(graph_token)
        if not is_user_eligible_for_role(eligibilities, role_definition_id):
            return json_response({"message": "Not eligible for role."}, 403)

        result = await activate_pim_role(
            graph_token=graph_token,
            principal_id=principal_id,
            role_definition_id=role_definition_id,
            activation=activation,
        )
    except httpx.HTTPStatusError as exc:
        if is_already_active_graph_error(exc.response):
            return json_response({"message": "PIM is already activated."}, 200)
        if is_not_eligible_graph_error(exc.response):
            return json_response({"message": "Not eligible for role."}, 403)

        logging.warning("Graph request failed: %s", exc.response.text)
        return func.HttpResponse(
            exc.response.text,
            status_code=exc.response.status_code,
            mimetype="application/json",
            headers=cors_headers(),
        )
    except Exception as exc:
        logging.exception("PIM activation failed")
        return json_response({"error": "PIM activation failed", "details": str(exc)}, 500)

    logging.info(
        "PIM activation requested. user=%s role=%s ticket=%s status=%s",
        principal_id,
        activation.role_name,
        activation.ticket_number,
        result.get("status"),
    )

    return func.HttpResponse(
        json.dumps(result),
        status_code=201,
        mimetype="application/json",
        headers=cors_headers(),
    )


def is_already_active_graph_error(response: httpx.Response) -> bool:
    try:
        graph_error = response.json().get("error", {})
    except ValueError:
        graph_error = {}

    code = str(graph_error.get("code", "")).lower()
    message = str(graph_error.get("message", "")).lower()
    combined = f"{code} {message}"

    already_signal = "already" in combined or "exist" in combined
    pim_signal = (
        "active" in combined
        or "activation" in combined
        or "assignment" in combined
        or "schedule" in combined
    )

    return response.status_code in {400, 409} and already_signal and pim_signal


def is_user_eligible_for_role(eligibilities: list[dict], role_definition_id: str) -> bool:
    return any(
        eligibility.get("roleDefinitionId") == role_definition_id
        and str(eligibility.get("status", "")).lower() == "provisioned"
        for eligibility in eligibilities
    )


def is_not_eligible_graph_error(response: httpx.Response) -> bool:
    try:
        graph_error = response.json().get("error", {})
    except ValueError:
        graph_error = {}

    code = str(graph_error.get("code", "")).lower()
    message = str(graph_error.get("message", "")).lower()
    combined = f"{code} {message}"

    return response.status_code in {400, 403, 404} and (
        "roleassignmentdoesnotexist" in combined
        or "role assignment does not exist" in combined
        or "eligible" in combined
        or "eligibility" in combined
    )
