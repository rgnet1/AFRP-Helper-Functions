"""Bundled frontend assets for badge templates (served inline, not via /static mount)."""

from __future__ import annotations

import os

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


def load_badge_scale_js() -> str:
    """Return badge_scale.js bundled with the app (survives stale static volume mounts)."""
    path = os.path.join(_ASSETS_DIR, "badge_scale.js")
    with open(path, encoding="utf-8") as fh:
        return fh.read()
