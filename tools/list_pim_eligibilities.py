import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

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
    if TOKEN_PATH.exists():
        return validate_jwt_shape(TOKEN_PATH.read_text(encoding="utf-8"))

    raise RuntimeError("Run tools/get_user_token.py first.")


def validate_jwt_shape(token: str) -> str:
    token = token.strip().strip('"').strip("'")
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1].strip()

    if token.count(".") != 2:
        raise RuntimeError("Saved token is not shaped like a JWT. Run tools/get_user_token.py again.")

    return token


async def main() -> None:
    load_local_settings()

    from shared.auth import acquire_graph_token_on_behalf_of
    from shared.graph import (
        get_current_user,
        get_current_user_eligibilities,
        get_role_definition,
    )

    graph_token = acquire_graph_token_on_behalf_of(get_user_token())
    user = await get_current_user(graph_token)
    try:
        eligibilities = await get_current_user_eligibilities(graph_token)
    except httpx.HTTPStatusError as exc:
        print(f"Graph eligibility lookup failed: {exc.response.status_code}")
        print(exc.response.text)
        raise

    print(f"Signed-in user: {user.get('displayName')} ({user.get('userPrincipalName')})")
    print(f"Principal ID: {user.get('id')}")
    print(f"Eligibility count: {len(eligibilities)}")

    for eligibility in eligibilities:
        role_definition_id = eligibility.get("roleDefinitionId")
        role_name = "<unknown>"
        if role_definition_id:
            try:
                role_definition = await get_role_definition(graph_token, role_definition_id)
                role_name = role_definition.get("displayName", role_name)
            except httpx.HTTPStatusError:
                role_name = "<lookup failed>"

        print()
        print(f"id: {eligibility.get('id')}")
        print(f"roleDefinitionId: {role_definition_id}")
        print(f"roleName: {role_name}")
        print(f"directoryScopeId: {eligibility.get('directoryScopeId')}")
        print(f"appScopeId: {eligibility.get('appScopeId')}")
        print(f"status: {eligibility.get('status')}")
        print(f"memberType: {eligibility.get('memberType')}")
        print(f"createdUsing: {eligibility.get('createdUsing')}")


if __name__ == "__main__":
    asyncio.run(main())
