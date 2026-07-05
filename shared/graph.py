from datetime import datetime, timezone

import httpx

from shared.config import settings
from shared.models import PimActivationRequest

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


async def get_current_user(graph_token: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{GRAPH_BASE_URL}/me?$select=id,userPrincipalName,displayName",
            headers={"Authorization": f"Bearer {graph_token}"},
        )

    response.raise_for_status()
    return response.json()


async def get_current_user_eligibilities(graph_token: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{GRAPH_BASE_URL}/roleManagement/directory/roleEligibilitySchedules/filterByCurrentUser(on='principal')",
            headers={"Authorization": f"Bearer {graph_token}"},
        )

    response.raise_for_status()
    return response.json().get("value", [])


async def get_role_definition(graph_token: str, role_definition_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{GRAPH_BASE_URL}/roleManagement/directory/roleDefinitions/{role_definition_id}",
            headers={"Authorization": f"Bearer {graph_token}"},
        )

    response.raise_for_status()
    return response.json()


async def activate_pim_role(
    graph_token: str,
    principal_id: str,
    role_definition_id: str,
    activation: PimActivationRequest,
) -> dict:
    payload = {
        "action": "selfActivate",
        "principalId": principal_id,
        "roleDefinitionId": role_definition_id,
        "directoryScopeId": "/",
        "justification": activation.justification or activation.ticket_number,
        "scheduleInfo": {
            "startDateTime": datetime.now(timezone.utc).isoformat(),
            "expiration": {
                "type": "AfterDuration",
                "duration": f"PT{activation.duration_hours}H",
            },
        },
        "ticketInfo": {
            "ticketNumber": activation.ticket_number,
            "ticketSystem": settings.ticket_system_name,
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{GRAPH_BASE_URL}/roleManagement/directory/roleAssignmentScheduleRequests",
            headers={
                "Authorization": f"Bearer {graph_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    response.raise_for_status()
    return response.json()
