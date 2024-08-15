import string
import secrets
import os
import json
from typing import Dict, Annotated
from datetime import datetime, timedelta
from urllib.parse import urlencode

from fastapi import Depends, Cookie, Form, Request, HTTPException
from fastapi import APIRouter
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import APIKeyHeader, APIKeyQuery
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

from server.constants import (
    KEY_FILE,
    SEED_KEY_FILE,
    API_KEY_HEADER_NAME,
    API_KEY_QUERY_NAME,
    API_KEY_COOKIE_NAME,
    COOKIE_EXPIRATION_DAYS,
    FLATMATES,
)
from server.telemetry import failed_login, send_message

router = APIRouter()

def generate_key(length=32):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def load_keys() -> Dict[str, str]:
    keys = {}
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE) as f:
            keys = json.load(f)

    if os.path.exists(SEED_KEY_FILE):
        with open(SEED_KEY_FILE) as f:
            seed_keys = json.load(f)
        keys = {**keys, **seed_keys}

    return keys


KEYS = load_keys()


# Security key header
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)
api_key_query = APIKeyQuery(name=API_KEY_QUERY_NAME, auto_error=False)
# Authentication function
async def get_api_key(
    api_key_header: str | None = Depends(api_key_header),
    api_key_cookie: str | None = Cookie(None, alias=API_KEY_COOKIE_NAME),
) -> str | None:
    return api_key_header or api_key_cookie

def get_user(request: Request) -> str:
    user = request.state.user

    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    return user


User = Annotated[str, Depends(get_user)]


def get_flatmate(user: User) -> str:
    if user not in FLATMATES:
        raise HTTPException(status_code=403, detail="Not authorized")
    return user


Flatmate = Annotated[str, Depends(get_flatmate)]


# Authentication middleware
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # List of paths that don't require authentication
        open_paths = ["/login", "/auth", "/favicon.ico"]

        query_param_key = request.query_params.get(API_KEY_QUERY_NAME)
        if query_param_key:
            user = next(
                (name for name, k in KEYS.items() if k == query_param_key), None
            )
            if user:
                # Set cookie to expire in 10 years
                expiration = datetime.utcnow() + timedelta(days=COOKIE_EXPIRATION_DAYS)

                # Preserve other query parameters if any
                query_params = dict(request.query_params)
                query_params.pop(API_KEY_QUERY_NAME, None)
                if query_params:
                    query_string = f"?{urlencode(query_params)}"
                else:
                    query_string = ""

                response = RedirectResponse(
                    # redirect to the same page to avoid the key being in the
                    #   url bar
                    url=f"{request.url.path}{query_string}",
                    status_code=303,
                )  # 303 See Other
                response.set_cookie(
                    key=API_KEY_COOKIE_NAME,
                    value=query_param_key,
                    expires=expiration.strftime("%a, %d %b %Y %H:%M:%S GMT"),
                    httponly=True,
                    samesite="lax",
                )
                return response

            else:
                failed_login(request, query_param_key)
                return RedirectResponse(url="/login?error=invalid_key", status_code=303)

        if request.url.path in open_paths:
            return await call_next(request)

        api_key = await get_api_key(
            api_key_header=request.headers.get(API_KEY_HEADER_NAME),
            api_key_cookie=request.cookies.get(API_KEY_COOKIE_NAME),
        )

        if api_key is None:
            if request.method == "POST":
                return JSONResponse(
                    status_code=401, content={"detail": "Authentication required"}
                )
            return RedirectResponse(url="/login")

        user = next((name for name, key in KEYS.items() if key == api_key), None)
        if user is None:
            if request.method == "POST":
                return JSONResponse(
                    status_code=403, content={"detail": "Invalid API Key"}
                )
            return RedirectResponse(url="/login")

        request.state.user = user
        response = await call_next(request)
        return response

class AddKeyParams(BaseModel):
    name: str


class DeleteKeyParams(BaseModel):
    name: str


@router.post("/auth")
async def auth(request: Request, key: str = Form(...)):
    user = next((name for name, k in KEYS.items() if k == key), None)
    if user:
        # Set cookie to expire in 10 years
        expiration = datetime.utcnow() + timedelta(days=COOKIE_EXPIRATION_DAYS)
        response = RedirectResponse(url="/", status_code=303)  # 303 See Other
        response.set_cookie(
            key=API_KEY_COOKIE_NAME,
            value=key,
            expires=expiration.strftime("%a, %d %b %Y %H:%M:%S GMT"),
            httponly=True,  # Makes the cookie inaccessible to JavaScript
            samesite="lax",  # Provides some CSRF protection
        )
        send_message(f"{user} logged in via /auth")
        return response

    failed_login(request, key)
    return RedirectResponse(
        url="/login?error=invalid_key", status_code=303
    )  # 303 See Other


@router.get("/api/keys")
def get_keys_handler(
    flatmate: Flatmate,
):
    return list(KEYS.items())


@router.post("/api/keys")
def add_keys(
    AddKeyParams: AddKeyParams,
    flatmate: Flatmate,
):
    key = generate_key()
    KEYS[AddKeyParams.name] = key

    with open(KEY_FILE, "w") as f:
        json.dump(KEYS, f, indent=2)

    send_message(f"{flatmate} added key for {AddKeyParams.name}")

    return {"message": "Key added", "key": key, "name": AddKeyParams.name}


@router.delete("/api/keys")
def delete_keys(
    DeleteKeyParams: DeleteKeyParams,
    flatmate: Flatmate,
):
    if DeleteKeyParams.name in FLATMATES:
        return {"message": "Cannot delete flatmate keys"}

    key = KEYS.pop(DeleteKeyParams.name, None)

    with open(KEY_FILE, "w") as f:
        json.dump(KEYS, f, indent=2)

    send_message(f"{flatmate} deleted key for {DeleteKeyParams.name}")

    return {"message": "Key deleted", "key": key, "name": DeleteKeyParams.name}
