"""Concrete SMS gateway client: one HTTPS request per message."""

from __future__ import annotations

import http.client
import json

DEFAULT_HOST = "sms-gateway.clinic.internal"


class SmsGateway:
    """Sends text messages through the provider's HTTP API.

    Construction only stores settings; the connection opens inside ``send``.
    """

    def __init__(self, host: str = DEFAULT_HOST, timeout: float = 5.0) -> None:
        self._host = host
        self._timeout = timeout

    def send(self, phone: str, body: str) -> None:
        connection = http.client.HTTPSConnection(self._host, timeout=self._timeout)
        try:
            payload = json.dumps({"to": phone, "body": body})
            headers = {"Content-Type": "application/json"}
            connection.request("POST", "/v1/messages", payload, headers)
            response = connection.getresponse()
            if response.status >= 300:
                raise RuntimeError(f"SMS gateway refused message to {phone}: {response.status}")
        finally:
            connection.close()
