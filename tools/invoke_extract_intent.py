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


async def main() -> None:
    body = {
        "message": "Activate my AI Reader role for 2 hours for Ticket12345."
    }

    req = func.HttpRequest(
        method="POST",
        url="/api/intent/extract",
        headers={"Authorization": "Bearer fake-user-token"},
        params={},
        route_params={},
        body=json.dumps(body).encode("utf-8"),
    )

    response = await function_app.extract_intent(req)
    print(f"Status: {response.status_code}")
    print(response.get_body().decode("utf-8"))


if __name__ == "__main__":
    asyncio.run(main())
