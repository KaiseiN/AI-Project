import json
import logging

import azure.functions as func
import httpx
from pydantic import ValidationError

from shared.auth import acquire_graph_token_on_behalf_of, get_bearer_token
from shared.config import settings
from shared.graph import activate_pim_role, get_current_user
from shared.models import PimActivationRequest
from shared.responses import json_response
from shared.tickets import validate_ticket

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="pim/activate", methods=["POST"])
async def activate_pim(req: func.HttpRequest) -> func.HttpResponse:
    try:
        activation = PimActivationRequest.model_validate(req.get_json())
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

    bearer_token = get_bearer_token(req)
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
        result = await activate_pim_role(
            graph_token=graph_token,
            principal_id=principal_id,
            role_definition_id=role_definition_id,
            activation=activation,
        )
    except httpx.HTTPStatusError as exc:
        if is_already_active_graph_error(exc.response):
            return json_response({"message": "pim is already activated"}, 200)

        logging.warning("Graph request failed: %s", exc.response.text)
        return func.HttpResponse(
            exc.response.text,
            status_code=exc.response.status_code,
            mimetype="application/json",
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
