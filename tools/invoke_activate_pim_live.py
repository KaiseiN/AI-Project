import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TOKEN_PATH = ROOT / ".local" / "user_access_token.txt"


def load_local_settings() -> None:
    settings_path = ROOT / "local.settings.json"
    with settings_path.open("r", encoding="utf-8") as settings_file:
        settings = json.load(settings_file)

    for key, value in settings.get("Values", {}).items():
        os.environ.setdefault(key, value)


def get_user_token() -> str:
    if len(sys.argv) > 1:
        return validate_jwt_shape(sys.argv[1])

    if TOKEN_PATH.exists():
        return validate_jwt_shape(TOKEN_PATH.read_text(encoding="utf-8"))

    token = os.getenv("PIM_API_BEARER_TOKEN")
    if token:
        return validate_jwt_shape(token)

    raise RuntimeError(
        "Provide a user access token, set PIM_API_BEARER_TOKEN, or run tools/get_user_token.py first."
    )


def validate_jwt_shape(token: str) -> str:
    token = token.strip().strip('"').strip("'")
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1].strip()

    if token.count(".") != 2:
        raise RuntimeError(
            "The supplied token is not shaped like a JWT. Run tools/get_user_token.py "
            "and let tools/invoke_activate_pim_live.py read the saved token file."
        )

    return token


async def main() -> None:
    load_local_settings()

    import azure.functions as func
    import function_app

    body = {
        "roleName": "AI Reader",
        "durationHours": 2,
        "ticketNumber": "#12345",
        "justification": "#12345",
    }

    req = func.HttpRequest(
        method="POST",
        url="/api/pim/activate",
        headers={"Authorization": f"Bearer {get_user_token()}"},
        params={},
        route_params={},
        body=json.dumps(body).encode("utf-8"),
    )

    response = await function_app.activate_pim(req)
    print(f"Status: {response.status_code}")
    print(response.get_body().decode("utf-8"))


if __name__ == "__main__":
    asyncio.run(main())
