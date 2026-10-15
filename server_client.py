import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class ServerAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ServerClient:
    """Client for the optional SpotLight server API."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (
            base_url or os.environ.get("SPOTLIGHT_API_BASE_URL", "")
        ).rstrip("/")

        if not self.base_url:
            raise ServerAPIError(
                "Set SPOTLIGHT_API_BASE_URL before connecting to the server."
            )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        access_token: str | None = None,
    ) -> Any:
        headers = {"Accept": "application/json"}
        body = None

        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urlopen(request, timeout=10) as response:
                raw = response.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except HTTPError as error:
            try:
                body_data = json.loads(error.read().decode("utf-8"))
                detail = body_data.get("detail", error.reason)
            except (json.JSONDecodeError, UnicodeDecodeError):
                detail = error.reason
            raise ServerAPIError(str(detail), error.code) from error
        except (URLError, TimeoutError, OSError) as error:
            raise ServerAPIError(
                f"Could not reach the SpotLight server: {error}"
            ) from error
        except json.JSONDecodeError as error:
            raise ServerAPIError(
                "The server returned an invalid response."
            ) from error

    def register(
        self, email: str, username: str, password: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/auth/register",
            {"email": email, "username": username, "password": password},
        )

    def login(self, identifier: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/auth/login",
            {"identifier": identifier, "password": password},
        )

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/auth/refresh",
            {"refresh_token": refresh_token},
        )

    def revoke(self, refresh_token: str) -> Any:
        return self._request(
            "POST",
            "/auth/revoke",
            {"refresh_token": refresh_token},
        )

    def get_profile(self, access_token: str) -> dict[str, Any]:
        return self._request("GET", "/me", access_token=access_token)

    def list_favorites(self, access_token: str) -> list[dict[str, Any]]:
        return self._request(
            "GET", "/favorites", access_token=access_token
        )

    def add_favorite(
        self, access_token: str, category: str, provider_id: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/favorites",
            {"category": category, "provider_id": provider_id},
            access_token=access_token,
        )

    def remove_favorite(self, access_token: str, favorite_id: str) -> None:
        self._request(
            "DELETE",
            f"/favorites/{quote(favorite_id, safe='')}",
            access_token=access_token,
        )