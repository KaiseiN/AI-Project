import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("AZURE_TENANT_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("AZURE_CLIENT_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("AZURE_CLIENT_SECRET", "local-test-secret")
os.environ.setdefault("TICKET_SYSTEM_NAME", "ConnectWise")
os.environ.setdefault("MAX_PIM_DURATION_HOURS", "4")

import azure.functions as func
import function_app
from shared.config import settings


async def fake_get_current_user(graph_token: str) -> dict:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "userPrincipalName": "test.user@example.com",
        "displayName": "Test User",
    }


async def fake_activate_pim_role(
    graph_token: str,
    principal_id: str,
    role_definition_id: str,
    activation,
) -> dict:
    return {
        "id": "22222222-2222-2222-2222-222222222222",
        "status": "Provisioned",
        "action": "selfActivate",
        "principalId": principal_id,
        "roleDefinitionId": role_definition_id,
        "justification": activation.justification or activation.ticket_number,
        "ticketInfo": {
            "ticketNumber": activation.ticket_number,
            "ticketSystem": settings.ticket_system_name,
        },
    }


async def main() -> None:
    function_app.acquire_graph_token_on_behalf_of = lambda token: "fake-graph-token"
    function_app.get_current_user = fake_get_current_user
    function_app.activate_pim_role = fake_activate_pim_role

    body = {
        "roleName": "AI Reader",
        "durationHours": 2,
        "ticketNumber": "#12345",
        "justification": "#12345",
    }

    req = func.HttpRequest(
        method="POST",
        url="/api/pim/activate",
        headers={"Authorization": "Bearer fake-user-token"},
        params={},
        route_params={},
        body=json.dumps(body).encode("utf-8"),
    )

    response = await function_app.activate_pim(req)
    print(f"Status: {response.status_code}")
    print(response.get_body().decode("utf-8"))


if __name__ == "__main__":
    asyncio.run(main())
