import logging
import requests

from server.constants import NTFY_TOPIC

_logger = logging.getLogger(__name__)


def send_message(msg: str, topic: str | None = None):
    topic = topic or NTFY_TOPIC
    _logger.info(msg)
    try:
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=msg,
        )
    except Exception as e:
        _logger.error(f"Failed to send ntfy message: {e}")


def failed_login(request, key):
    send_message(
        f"Someone tried to access with an invalid key: {key}, "
        f"IP: {request.client.host}"
    )
