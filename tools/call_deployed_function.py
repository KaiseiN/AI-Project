import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATH = ROOT / ".local" / "user_access_token.txt"


def get_function_url() -> str:
    if len(sys.argv) > 1:
        return validate_function_url(sys.argv[1])

    function_url = os.getenv("PIM_FUNCTION_URL")
    if function_url:
        return validate_function_url(function_url)

    raise RuntimeError(
        "Provide the Function URL as the first argument or set PIM_FUNCTION_URL."
    )


def validate_function_url(function_url: str) -> str:
    function_url = function_url.strip().strip('"').strip("'")
    parsed = urlparse(function_url)

    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise RuntimeError(
            "Function URL must be a full URL like "
            "https://your-function-app.azurewebsites.net/api/pim/activate"
        )

    if "<" in function_url or ">" in function_url:
        raise RuntimeError("Replace the placeholder Function URL with your real Azure Function URL.")

    return function_url


def get_user_token() -> str:
    if not TOKEN_PATH.exists():
        raise RuntimeError("Run tools/get_user_token.py first.")

    return validate_jwt_shape(TOKEN_PATH.read_text(encoding="utf-8"))


def validate_jwt_shape(token: str) -> str:
    token = token.strip().strip('"').strip("'")
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1].strip()

    if token.count(".") != 2:
        raise RuntimeError("Saved token is not shaped like a JWT. Run tools/get_user_token.py again.")

    return token


async def main() -> None:
    function_url = get_function_url()
    user_token = get_user_token()
    body = {
        "roleName": "AI Reader",
        "durationHours": 2,
        "ticketNumber": "Ticket12345",
        "justification": "Ticket12345",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.post(
                function_url,
                headers={
                    "Authorization": f"Bearer {user_token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        except httpx.ConnectError as exc:
            host = urlparse(function_url).netloc
            raise RuntimeError(
                f"Could not connect to {host}. Check the Function App name in the URL "
                "and confirm the app is running."
            ) from exc

    print(f"Status: {response.status_code}")

    try:
        response_body = response.json()
        print(json.dumps(response_body, indent=2))
    except ValueError:
        if response.text:
            print(response.text)
        else:
            print("<empty response body>")
        response_body = {}

    if response.status_code == 401 and "audience validation failed" in str(response_body).lower():
        claims = decode_jwt_claims(user_token)
        print()
        print("Token audience rejected by Function App authentication.")
        print(f"Token aud: {claims.get('aud')}")
        print("Add that value to the Function App authentication provider's allowed token audiences.")

    if response.status_code in {401, 403}:
        print_auth_diagnostics(response, user_token)


def decode_jwt_claims(token: str) -> dict:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")))


def print_auth_diagnostics(response: httpx.Response, token: str) -> None:
    claims = decode_jwt_claims(token)
    print()
    print("Auth diagnostics:")
    print(f"Token aud: {claims.get('aud')}")
    print(f"Token scp: {claims.get('scp')}")
    print(f"Token appid: {claims.get('appid')}")
    print(f"Token upn: {claims.get('upn') or claims.get('unique_name')}")

    for header_name in (
        "www-authenticate",
        "x-ms-error-code",
        "x-ms-client-principal-id",
        "x-ms-client-principal-name",
    ):
        value = response.headers.get(header_name)
        if value:
            print(f"{header_name}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
