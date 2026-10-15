"""afrp — CLI for AFRP CRM Helper."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import click

from afrp_cli import __version__
from afrp_cli.client import ApiError, Client, guess_mime
from afrp_cli.context import Ctx, exit_api, pass_ctx

HELP_OPTS = {"help_option_names": ["-h", "--help"]}
CONFIG_PATH = Path(os.environ.get("AFRP_CONFIG", Path.home() / ".config" / "afrp-helper" / "config.json"))


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.is_file():
        return json.loads(CONFIG_PATH.read_text())
    return {"default": "default", "profiles": {}}


def save_config(cfg: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
    CONFIG_PATH.chmod(0o600)


def resolve_profile(name: str | None, base_url: str | None, api_key: str | None) -> tuple[str, str, str]:
    base_url = base_url or os.environ.get("AFRP_BASE_URL")
    api_key = api_key or os.environ.get("AFRP_API_KEY")
    profile_name = name or os.environ.get("AFRP_PROFILE")
    if base_url and api_key:
        return base_url.rstrip("/"), api_key, profile_name or "(flags)"
    cfg = load_config()
    pname = profile_name or cfg.get("default") or "default"
    prof = (cfg.get("profiles") or {}).get(pname)
    if not prof:
        raise click.ClickException(
            f"No profile {pname!r}. Run: afrp setup user --name {pname} --base-url URL --api-key afrp_..."
        )
    return prof["base_url"].rstrip("/"), prof["api_key"], pname


@click.group(context_settings=HELP_OPTS)
@click.option("--profile", help="Named profile from ~/.config/afrp-helper/config.json")
@click.option("--base-url", help="API origin (overrides profile)")
@click.option("--api-key", help="API key afrp_... (overrides profile)")
@click.version_option(__version__, prog_name="afrp")
@click.pass_context
def main(ctx: click.Context, profile: str | None, base_url: str | None, api_key: str | None) -> None:
    """AFRP CRM Helper CLI. Use `afrp COMMAND -h` for help."""
    if ctx.invoked_subcommand not in ("setup", "update", "help"):
        ctx.obj = Ctx(profile, base_url, api_key, resolve_profile)


@main.group("setup", context_settings=HELP_OPTS)
def setup_group() -> None:
    """Manage profiles (base URL + API key)."""


@setup_group.command("user")
@click.option("--name", "names", multiple=True, help="Profile name (repeat for multiple)")
@click.option("--base-url", "base_urls", multiple=True, help="Helper URL (repeat with --name)")
@click.option("--api-key", "api_keys", multiple=True, help="API key afrp_... (repeat with --name)")
@click.option("--default", "make_default", is_flag=True, help="Set the first profile as default")
def setup_user(names: tuple[str, ...], base_urls: tuple[str, ...], api_keys: tuple[str, ...], make_default: bool) -> None:
    """Save one or more profiles. Each key is checked with GET /api/me."""
    if not names:
        names = (click.prompt("Profile name"),)
    if len(base_urls) == 1 and len(names) > 1:
        base_urls = base_urls * len(names)
    if len(api_keys) == 1 and len(names) > 1:
        api_keys = api_keys * len(names)
    if len(names) != len(base_urls) or len(names) != len(api_keys):
        raise click.ClickException("Provide matching --name, --base-url, and --api-key counts")

    cfg = load_config()
    profiles = cfg.setdefault("profiles", {})
    for profile_name, url, key in zip(names, base_urls, api_keys):
        try:
            who = Client(url, key).json("GET", "/api/me")
        except ApiError as exc:
            exit_api(exc)
        profiles[profile_name] = {"base_url": url.rstrip("/"), "api_key": key}
        click.echo(f"Saved profile {profile_name!r} as {who.get('username', who.get('id'))}")
    if make_default or len(names) == 1:
        cfg["default"] = names[0]
    save_config(cfg)


@setup_group.command("list")
def setup_list() -> None:
    """List saved profiles (keys redacted)."""
    cfg = load_config()
    default = cfg.get("default")
    rows = []
    for name, profile in (cfg.get("profiles") or {}).items():
        key = profile.get("api_key", "")
        rows.append({
            "name": name,
            "base_url": profile.get("base_url"),
            "key": (key[:12] + "…") if len(key) > 12 else "…",
            "default": name == default,
        })
    click.echo(json.dumps({"default": default, "profiles": rows}, indent=2))


@setup_group.command("use")
@click.argument("name")
def setup_use(name: str) -> None:
    """Set the default profile."""
    cfg = load_config()
    if name not in (cfg.get("profiles") or {}):
        raise click.ClickException(f"Unknown profile {name!r}")
    cfg["default"] = name
    save_config(cfg)
    click.echo(f"Default profile: {name}")


@setup_group.command("remove")
@click.argument("name")
def setup_remove(name: str) -> None:
    """Delete a profile."""
    cfg = load_config()
    profiles = cfg.get("profiles") or {}
    if name not in profiles:
        raise click.ClickException(f"Unknown profile {name!r}")
    del profiles[name]
    if cfg.get("default") == name:
        cfg["default"] = next(iter(profiles), None)
    save_config(cfg)
    click.echo(f"Removed profile {name!r}")


@setup_group.command("test")
@click.option("--profile", help="Profile to test (default: the active default)")
def setup_test(profile: str | None) -> None:
    """Verify a profile with GET /api/me."""
    url, key, pname = resolve_profile(profile, None, None)
    try:
        data = Client(url, key).json("GET", "/api/me")
    except ApiError as exc:
        exit_api(exc)
    click.echo(json.dumps({"profile": pname, **data}, indent=2))


@main.command("help")
@click.argument("topic", required=False)
@click.pass_context
def help_cmd(ctx: click.Context, topic: str | None) -> None:
    """Show help. Example: afrp help seating"""
    parent = ctx.parent
    if parent is None:
        raise click.ClickException("Help is unavailable")
    if not topic:
        click.echo(parent.get_help())
        return
    command = parent.command.get_command(parent, topic) if isinstance(parent.command, click.Group) else None
    if command is None:
        raise click.ClickException(f"Unknown command {topic!r}. Run: afrp help")
    with click.Context(command, info_name=topic, parent=parent) as sub:
        click.echo(command.get_help(sub))


@main.command("update")
@click.option("--check", is_flag=True, help="Only print current vs latest; do not install")
@click.option("-y", "--yes", "assume_yes", is_flag=True, help="Install without confirmation")
def update_cmd(check: bool, assume_yes: bool) -> None:
    """Check GitHub for a newer cli-v* release and upgrade via pipx."""
    from afrp_cli.updater import resolve_version_info, run_pipx_install

    try:
        info = resolve_version_info(__version__)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    if not info.update_available:
        click.echo(f"afrp {info.current} (latest)")
        return

    click.echo(f"{info.current} → {info.latest} available ({info.latest_tag}).")
    if check:
        return
    if not assume_yes and not click.confirm("Update?", default=False):
        click.echo("Cancelled.")
        return
    try:
        run_pipx_install(info.latest_tag)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Updated to afrp {info.latest}. Re-run your command.")


@main.command("whoami")
@pass_ctx
def whoami_cmd(ctx: Ctx) -> None:
    """Show the signed-in user."""
    try:
        ctx.show(ctx.client.json("GET", "/api/me"))
    except ApiError as exc:
        exit_api(exc)


@main.command("commands")
@pass_ctx
def commands_cmd(ctx: Ctx) -> None:
    """List API commands this key is allowed to call."""
    try:
        ctx.show(ctx.client.json("GET", "/api"))
    except ApiError as exc:
        exit_api(exc)


@main.command("openapi")
@click.option("-o", "--output", type=click.Path(), help="Write the spec to a file instead of stdout")
@pass_ctx
def openapi_cmd(ctx: Ctx, output: str | None) -> None:
    """Download the live OpenAPI spec."""
    try:
        resp = ctx.client.request("GET", "/openapi.yaml")
    except ApiError as exc:
        exit_api(exc)
    if output:
        Path(output).write_text(resp.text)
        click.echo(f"Wrote {output}")
    else:
        click.echo(resp.text)


@main.command("call")
@click.argument("method")
@click.argument("path")
@click.option("--query", "-q", multiple=True, help="Query parameter key=value")
@click.option("--data", "-d", help="JSON body")
@click.option("--form", "-F", multiple=True, help="Form field key=value or key=@file")
@click.option("-o", "--output", type=click.Path(), help="Write the response body to a file")
@pass_ctx
def call_cmd(
    ctx: Ctx,
    method: str,
    path: str,
    query: tuple[str, ...],
    data: str | None,
    form: tuple[str, ...],
    output: str | None,
) -> None:
    """Call any API route.

    Examples:

      afrp call GET /api/me

      afrp call POST /api/seating/EVENT/assign -d '{"contact_id":"...","table_id":"..."}'
    """
    params = {}
    for item in query:
        if "=" not in item:
            raise click.ClickException(f"Bad --query {item!r}, use key=value")
        key, value = item.split("=", 1)
        params[key] = value
    json_body = json.loads(data) if data else None
    form_data: dict[str, str] = {}
    files = None
    if form:
        files = {}
        for item in form:
            if "=" not in item:
                raise click.ClickException(f"Bad --form {item!r}, use key=value or key=@file")
            key, value = item.split("=", 1)
            if value.startswith("@"):
                file_path = Path(value[1:])
                files[key] = (file_path.name, file_path.read_bytes(), guess_mime(file_path))
            else:
                form_data[key] = value
    try:
        resp = ctx.client.request(
            method,
            path,
            params=params or None,
            json_body=None if form else json_body,
            data=form_data or None,
            files=files,
        )
        if output:
            Path(output).write_bytes(resp.content)
            click.echo(json.dumps({"saved": output, "bytes": len(resp.content)}, indent=2))
        elif "application/json" in resp.headers.get("content-type", ""):
            ctx.show(resp.json())
        else:
            click.echo(resp.text[:2000] if len(resp.text) < 2000 else resp.text[:2000] + "…")
    except ApiError as exc:
        exit_api(exc)


from afrp_cli.groups import register as register_groups

register_groups(main)


if __name__ == "__main__":
    try:
        main()
    except click.ClickException as exc:
        click.echo(f"error: {exc.message}", err=sys.stderr)
        sys.exit(1)
