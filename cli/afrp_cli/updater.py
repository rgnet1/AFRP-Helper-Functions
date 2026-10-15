"""Self-update helpers for the afrp CLI (pipx + GitHub cli-v* tags)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

CLI_PACKAGE_NAME = "afrp-helper-cli"
DEFAULT_GIT_SSH = "git@github.com:rgnet1/AFRP-Helper-Functions.git"
GITHUB_REPO = "rgnet1/AFRP-Helper-Functions"
TAG_RE = re.compile(r"^cli-v(\d+\.\d+\.\d+)$")


@dataclass(frozen=True)
class VersionInfo:
    current: str
    latest: str
    latest_tag: str

    @property
    def update_available(self) -> bool:
        return _parse_version(self.latest) > _parse_version(self.current)


def _parse_version(raw: str) -> tuple[int, int, int]:
    parts = raw.strip().lstrip("v").split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version: {raw!r}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def git_ssh_url() -> str:
    return os.environ.get("AFRP_CLI_GIT_URL", DEFAULT_GIT_SSH).strip() or DEFAULT_GIT_SSH


def pipx_available() -> bool:
    return shutil.which("pipx") is not None


def is_pipx_installed() -> bool:
    if not pipx_available():
        return False
    try:
        proc = subprocess.run(
            ["pipx", "list", "--json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if proc.returncode != 0 or not proc.stdout.strip():
        return False
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False
    venvs = data.get("venvs") if isinstance(data, dict) else None
    return isinstance(venvs, dict) and CLI_PACKAGE_NAME in venvs


def fetch_latest_cli_tag() -> tuple[str, str]:
    """Return (tag, version) for the highest cli-vX.Y.Z tag."""
    tags = _tags_via_git_ls_remote()
    if not tags:
        tags = _tags_via_github_api()
    if not tags:
        tags = _tags_via_gh_cli()
    if not tags:
        raise RuntimeError(
            "Could not list cli-v* tags. Check SSH access to the repo "
            f"({git_ssh_url()}) or set GITHUB_TOKEN / install gh."
        )
    best_tag, best_ver = max(tags, key=lambda item: _parse_version(item[1]))
    return best_tag, best_ver


def _tags_from_refs(lines: list[str]) -> list[tuple[str, str]]:
    found = []
    for line in lines:
        parts = line.split()
        if len(parts) < 2:
            continue
        ref = parts[-1]
        if ref.endswith("^{}"):
            continue
        name = ref.rsplit("/", 1)[-1]
        match = TAG_RE.match(name)
        if match:
            found.append((name, match.group(1)))
    return found


def _tags_via_git_ls_remote() -> list[tuple[str, str]]:
    if not shutil.which("git"):
        return []
    try:
        proc = subprocess.run(
            ["git", "ls-remote", "--tags", git_ssh_url(), "refs/tags/cli-v*"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return _tags_from_refs(proc.stdout.splitlines())


def _tags_via_github_api() -> list[tuple[str, str]]:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        return []
    try:
        import urllib.request

        req = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=50",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "afrp-helper-cli-updater",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    found = []
    for rel in payload:
        if not isinstance(rel, dict):
            continue
        tag = str(rel.get("tag_name") or "")
        match = TAG_RE.match(tag)
        if match:
            found.append((tag, match.group(1)))
    return found


def _tags_via_gh_cli() -> list[tuple[str, str]]:
    if not shutil.which("gh"):
        return []
    try:
        proc = subprocess.run(
            ["gh", "release", "list", "--repo", GITHUB_REPO, "--limit", "50"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    found = []
    for line in proc.stdout.splitlines():
        cols = line.split("\t")
        if len(cols) < 2:
            continue
        tag = cols[1].strip()
        match = TAG_RE.match(tag)
        if match:
            found.append((tag, match.group(1)))
    return found


def install_spec_for_tag(tag: str) -> str:
    return f"git+ssh://git@github.com/rgnet1/AFRP-Helper-Functions.git@{tag}#subdirectory=cli"


def run_pipx_install(tag: str) -> None:
    if not pipx_available():
        raise RuntimeError(
            "pipx is not installed. Install it first (e.g. sudo apt install pipx && pipx ensurepath), "
            "then re-run: afrp update"
        )
    if not is_pipx_installed():
        raise RuntimeError(
            "afrp-helper-cli is not installed via pipx. Bootstrap once with:\n"
            f'  pipx install "{install_spec_for_tag(tag)}"\n'
            "Then use `afrp update` for future upgrades."
        )
    proc = subprocess.run(
        ["pipx", "install", "--force", install_spec_for_tag(tag)],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(detail or f"pipx install failed for {tag}")


def resolve_version_info(current: str) -> VersionInfo:
    tag, latest = fetch_latest_cli_tag()
    return VersionInfo(current=current, latest=latest, latest_tag=tag)
