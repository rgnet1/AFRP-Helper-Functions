"""HTTP client for the AFRP CRM Helper API."""

from __future__ import annotations

import json
import mimetypes
import time
from pathlib import Path
from typing import Any

import httpx

_EXT_MIME_FALLBACK = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".zip": "application/zip",
}


def guess_mime(file_path: Path) -> str:
    guessed, _ = mimetypes.guess_type(file_path.name)
    if guessed:
        return guessed
    return _EXT_MIME_FALLBACK.get(file_path.suffix.lower(), "application/octet-stream")


class ApiError(Exception):
    def __init__(self, status: int, error: str, detail: str | None = None):
        self.status = status
        self.error = error
        self.detail = detail
        super().__init__(detail or error)


class Client:
    def __init__(self, base_url: str, api_key: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.timeout = timeout

    def url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}{path if path.startswith('/') else '/' + path}"

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: Any = None,
        data: dict[str, str] | None = None,
        files: Any = None,
        retries: int = 2,
    ) -> httpx.Response:
        url = self.url(path)
        last: httpx.Response | None = None
        for attempt in range(retries + 1):
            with httpx.Client(timeout=self.timeout) as http:
                last = http.request(
                    method.upper(),
                    url,
                    headers=self.headers,
                    params=params,
                    json=json_body,
                    data=data,
                    files=files,
                )
            if last.status_code not in (429, 500, 502, 503, 504) or attempt == retries:
                break
            wait = int(last.headers.get("Retry-After", "1"))
            time.sleep(max(1, wait))
        assert last is not None
        if last.status_code >= 400:
            err, detail = "Request failed", None
            try:
                body = last.json()
                if isinstance(body, dict):
                    err = str(body.get("error") or err)
                    extra = body.get("detail")
                    if extra is not None:
                        detail = str(extra)
            except json.JSONDecodeError:
                detail = last.text[:500] or None
            raise ApiError(last.status_code, err, detail)
        return last

    def json(self, method: str, path: str, **kwargs: Any) -> Any:
        return self.request(method, path, **kwargs).json()
