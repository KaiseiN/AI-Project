import json
import os

import azure.functions as func

DEFAULT_CORS_ORIGIN = "https://yellow-mushroom-01855d00f.7.azurestaticapps.net"


def cors_headers() -> dict:
    return {
        "Access-Control-Allow-Origin": os.getenv("CORS_ALLOWED_ORIGIN", DEFAULT_CORS_ORIGIN),
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "authorization, content-type",
        "Access-Control-Max-Age": "86400",
        "Vary": "Origin",
    }


def cors_preflight_response() -> func.HttpResponse:
    return func.HttpResponse(
        "",
        status_code=204,
        headers=cors_headers(),
    )


def json_response(payload: dict, status_code: int) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
        headers=cors_headers(),
    )
