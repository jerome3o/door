import json
import logging
import os

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from server.auth import Flatmate
from server.constants import FLATMATES, MAINTENANCE_FILE, MAINTENANCE_HTML_FILE
from server.telemetry import send_message

router = APIRouter()

_logger = logging.getLogger(__name__)


def is_maintenance_mode() -> bool:
    if not os.path.exists(MAINTENANCE_FILE):
        return False
    try:
        with open(MAINTENANCE_FILE) as f:
            return bool(json.load(f).get("enabled", False))
    except (json.JSONDecodeError, OSError):
        return False


def _set_maintenance_mode(enabled: bool) -> None:
    with open(MAINTENANCE_FILE, "w") as f:
        json.dump({"enabled": enabled}, f, indent=2)


def _format_flatmates() -> str:
    names = sorted(n.strip().capitalize() for n in FLATMATES if n.strip())
    if not names:
        return "one of the flatmates"
    tags = [f"<strong>{n}</strong>" for n in names]
    if len(tags) == 1:
        return tags[0]
    return ", ".join(tags[:-1]) + " or " + tags[-1]


def get_maintenance_page() -> str:
    with open(MAINTENANCE_HTML_FILE) as f:
        page = f.read()
    return page.replace("{{FLATMATES}}", _format_flatmates())


class MaintenanceParams(BaseModel):
    enabled: bool


@router.get("/api/maintenance")
def get_maintenance_status(flatmate: Flatmate):
    return {"enabled": is_maintenance_mode()}


@router.post("/api/maintenance")
def set_maintenance_status(params: MaintenanceParams, flatmate: Flatmate):
    _set_maintenance_mode(params.enabled)
    state = "ON" if params.enabled else "OFF"
    _logger.info(f"{flatmate} turned maintenance mode {state}")
    send_message(f"{flatmate} turned maintenance mode {state}")
    return {"message": f"Maintenance mode {state}", "enabled": params.enabled}
