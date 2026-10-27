import json
import mimetypes
import os
import uuid

import events
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class ServerAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


DEFAULT_API_BASE_URL = "http://192.168.1.151:8001/api/v1"


class ServerClient:
    """Client for the optional SpotLight server API."""

    @staticmethod
    def configured_base_url() -> str:
        """Use the saved app setting, development override, or home-beta default."""
        cfg = events.load_cfg()
        return str(
            cfg.get("server_api_base_url")
            or os.environ.get("SPOTLIGHT_API_BASE_URL", "")
            or DEFAULT_API_BASE_URL
        ).strip().rstrip("/")

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or self.configured_base_url()).rstrip("/")

        if not self.base_url:
            raise ServerAPIError("No SpotLight server address is configured.")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        access_token: str | None = None,
        timeout: int = 10,
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
            with urlopen(request, timeout=timeout) as response:
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

    def get_tmdb_catalog(self, access_token: str, since: int = 0) -> dict[str, Any]:
        return self._request(
            "GET", f"/catalog/tmdb?since={max(0, int(since))}", access_token=access_token
        )

    def refresh_tmdb_catalog(self, access_token: str) -> dict[str, Any]:
        return self._request(
            "POST", "/admin/catalog/tmdb/refresh", access_token=access_token, timeout=75
        )

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

    def update_profile(
        self, access_token: str, profile: dict[str, Any]
    ) -> dict[str, Any]:
        return self._request(
            "PATCH", "/me", profile, access_token=access_token
        )

    def upload_profile_avatar(self, access_token: str, file_path: str) -> dict[str, Any]:
        boundary = uuid.uuid4().hex
        with open(file_path, "rb") as avatar_file:
            image_data = avatar_file.read(4 * 1024 * 1024 + 1)
        if not image_data or len(image_data) > 4 * 1024 * 1024:
            raise ServerAPIError("Choose an image smaller than 4 MB.")
        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="profile-image"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("ascii") + image_data + f"\r\n--{boundary}--\r\n".encode("ascii")
        request = Request(
            f"{self.base_url}/me/avatar",
            data=body,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8")).get("detail", error.reason)
            except (json.JSONDecodeError, UnicodeDecodeError):
                detail = error.reason
            raise ServerAPIError(str(detail), error.code) from error
        except (URLError, TimeoutError, OSError) as error:
            raise ServerAPIError(f"Could not reach the SpotLight server: {error}") from error

    def delete_profile_avatar(self, access_token: str) -> None:
        self._request("DELETE", "/me/avatar", access_token=access_token)

    def get_public_profile(self, access_token: str, username: str) -> dict[str, Any]:
        return self._request(
            "GET", f"/profiles/{quote(username, safe='')}", access_token=access_token
        )

    def get_public_profile_avatar(self, access_token: str, username: str) -> bytes:
        request = Request(
            f"{self.base_url}/profiles/{quote(username, safe='')}/avatar",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "image/webp"},
        )
        try:
            with urlopen(request, timeout=15) as response:
                return response.read(100 * 1024 + 1)
        except HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8")).get("detail", error.reason)
            except (json.JSONDecodeError, UnicodeDecodeError):
                detail = error.reason
            raise ServerAPIError(str(detail), error.code) from error
        except (URLError, TimeoutError, OSError) as error:
            raise ServerAPIError(f"Could not reach the SpotLight server: {error}") from error

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

    def recover_username(self, email: str) -> dict[str, Any]:
        return self._request("POST", "/auth/recovery/username", {"email": email})

    def start_password_recovery(self, email: str) -> dict[str, Any]:
        return self._request("POST", "/auth/recovery/password", {"email": email})

    def complete_password_recovery(self, email: str, code: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/auth/recovery/password/complete",
            {"email": email, "code": code, "password": password},
        )

    def list_community_posts(
        self, access_token: str, category: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        query = f"?limit={limit}&offset={offset}"
        if category:
            query += "&category=" + quote(category, safe="")
        return self._request("GET", "/community/posts" + query, access_token=access_token)

    def create_community_post(
        self, access_token: str, category: str, title: str, body: str
    ) -> dict[str, Any]:
        return self._request(
            "POST", "/community/posts",
            {"category": category, "title": title, "body": body},
            access_token=access_token,
        )

    def upload_community_image(self, access_token: str, post_id: str, file_path: str) -> dict[str, Any]:
        boundary = uuid.uuid4().hex
        with open(file_path, "rb") as image_file:
            image_data = image_file.read(4 * 1024 * 1024 + 1)
        if not image_data or len(image_data) > 4 * 1024 * 1024:
            raise ServerAPIError("Each discussion photo must be smaller than 4 MB.")
        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="community-photo"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("ascii") + image_data + f"\r\n--{boundary}--\r\n".encode("ascii")
        request = Request(
            f"{self.base_url}/community/posts/{quote(post_id, safe='')}/images",
            data=body,
            headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}",
                     "Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            try: detail = json.loads(error.read().decode("utf-8")).get("detail", error.reason)
            except (json.JSONDecodeError, UnicodeDecodeError): detail = error.reason
            raise ServerAPIError(str(detail), error.code) from error
        except (URLError, TimeoutError, OSError) as error:
            raise ServerAPIError(f"Could not reach the SpotLight server: {error}") from error

    def list_community_images(self, access_token: str, post_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/community/posts/{quote(post_id, safe='')}/images", access_token=access_token)

    def get_community_image(self, access_token: str, post_id: str, image_id: str) -> bytes:
        request = Request(
            f"{self.base_url}/community/posts/{quote(post_id, safe='')}/images/{quote(image_id, safe='')}",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "image/webp"},
        )
        try:
            with urlopen(request, timeout=20) as response:
                return response.read(600 * 1024 + 1)
        except HTTPError as error:
            try: detail = json.loads(error.read().decode("utf-8")).get("detail", error.reason)
            except (json.JSONDecodeError, UnicodeDecodeError): detail = error.reason
            raise ServerAPIError(str(detail), error.code) from error
        except (URLError, TimeoutError, OSError) as error:
            raise ServerAPIError(f"Could not reach the SpotLight server: {error}") from error

    def list_community_replies(self, access_token: str, post_id: str) -> list[dict[str, Any]]:
        return self._request(
            "GET", f"/community/posts/{quote(post_id, safe='')}/replies", access_token=access_token
        )

    def create_community_reply(
        self, access_token: str, post_id: str, body: str
    ) -> dict[str, Any]:
        return self._request(
            "POST", f"/community/posts/{quote(post_id, safe='')}/replies",
            {"body": body}, access_token=access_token,
        )

    def report_community_content(
        self, access_token: str, target_type: str, target_id: str, reason: str
    ) -> dict[str, Any]:
        return self._request(
            "POST", "/community/reports",
            {"target_type": target_type, "target_id": target_id, "reason": reason},
            access_token=access_token,
        )

    def list_community_reports(self, access_token: str) -> list[dict[str, Any]]:
        return self._request("GET", "/admin/community/reports", access_token=access_token)

    def list_hidden_community_content(self, access_token: str) -> list[dict[str, Any]]:
        return self._request("GET", "/admin/community/hidden", access_token=access_token)

    def moderate_community_report(
        self, access_token: str, report_id: str, action: str, reason: str = ""
    ) -> dict[str, Any]:
        return self._request(
            "POST", f"/admin/community/reports/{quote(report_id, safe='')}/moderation",
            {"action": action, "reason": reason}, access_token=access_token,
        )

    def moderate_community_content(
        self, access_token: str, target_type: str, target_id: str,
        action: str = "hide", reason: str = "",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/admin/community/content/{quote(target_type, safe='')}/{quote(target_id, safe='')}/moderation",
            {"action": action, "reason": reason},
            access_token=access_token,
        )
