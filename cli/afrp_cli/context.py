"""Shared CLI context and event-id lookup."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import click

from afrp_cli.client import ApiError, Client

EVENT_HELP = "Sub-event id or name (discover via: afrp seating events)"
_UUID = re.compile(r"^[0-9a-fA-F-]{32,36}$")


def emit(data: Any) -> None:
    click.echo(json.dumps(data, indent=2))


def exit_api(err: ApiError) -> None:
    msg = err.error + (f": {err.detail}" if err.detail else "")
    if err.status == 401:
        raise click.ClickException(f"Unauthorized — {msg}")
    if err.status == 403:
        raise click.ClickException(f"Forbidden — {msg}")
    if err.status == 404:
        raise click.ClickException(f"Not found — {msg}")
    if err.status == 429:
        raise click.ClickException(f"Rate limited — {msg}")
    raise click.ClickException(f"HTTP {err.status} — {msg}")


def resolve_event_id(client: Client, event: str) -> str:
    if _UUID.match(event):
        return event
    try:
        payload = client.json("GET", "/api/seating/events")
    except ApiError as exc:
        exit_api(exc)
    found = []
    for parent in payload.get("events") or []:
        if parent.get("id") == event or parent.get("name") == event:
            found.append(parent)
        for child in parent.get("children") or []:
            if child.get("id") == event or child.get("name") == event:
                found.append(child)
    if len(found) == 1 and found[0].get("id"):
        return found[0]["id"]
    if len(found) > 1:
        raise click.ClickException(f"Event name {event!r} is ambiguous — use the id from: afrp seating events")
    raise click.ClickException(f"Unknown event {event!r}. Run: afrp seating events")


def _api(ctx: "Ctx", method: str, path: str, **kwargs: Any) -> Any:
    try:
        return ctx.client.json(method, path, **kwargs)
    except ApiError as exc:
        exit_api(exc)


def _get(ctx: "Ctx", path: str, params: dict[str, str] | None = None) -> None:
    ctx.show(_api(ctx, "GET", path, params=params))


def _send(ctx: "Ctx", method: str, path: str, body: Any = None, params: dict[str, str] | None = None) -> None:
    ctx.show(_api(ctx, method, path, json_body=body, params=params))


def _download(ctx: "Ctx", path: str, output: str, params: dict[str, str] | None = None) -> None:
    try:
        resp = ctx.client.request("GET", path, params=params)
        Path(output).write_bytes(resp.content)
        click.echo(json.dumps({"saved": output, "bytes": len(resp.content)}, indent=2))
    except ApiError as exc:
        exit_api(exc)


def _parse_json(data: str | None, required: bool = True) -> Any:
    if not data:
        if required:
            raise click.ClickException("--data JSON body is required")
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Invalid JSON: {exc}") from exc


class Ctx:
    def __init__(self, profile: str | None, base_url: str | None, api_key: str | None, resolve_profile_fn):
        self._profile = profile
        self._base_url = base_url
        self._api_key = api_key
        self._resolve_profile = resolve_profile_fn
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        if self._client is None:
            url, key, _name = self._resolve_profile(self._profile, self._base_url, self._api_key)
            self._client = Client(url, key)
        return self._client

    def show(self, data: Any) -> None:
        emit(data)


pass_ctx = click.make_pass_decorator(Ctx)
