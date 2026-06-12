#!/usr/bin/env python3
"""Validate Avery template specs fit on US Letter (8.5" × 11")."""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root: scripts/ → avery-badge-layouts/ → skills/ → .cursor/ → repo
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from utils.badges.badge_sizes import (  # noqa: E402
    AVERY_TEMPLATES,
    list_dropdown_templates,
    validate_avery_sheet_layout,
)


def main() -> int:
    codes = sys.argv[1:] or [t["code"] for t in list_dropdown_templates()]
    extra = [c for c in AVERY_TEMPLATES if c not in codes]
    codes = codes + extra

    failed = False
    print(f"{'Code':8} {'Size':14} {'Grid':6} {'Right':7} {'Bottom':7} {'OK'}")
    print("-" * 52)

    seen = set()
    for code in codes:
        if code in seen or code not in AVERY_TEMPLATES:
            continue
        seen.add(code)
        spec = AVERY_TEMPLATES[code]
        v = validate_avery_sheet_layout(spec)
        ok = v["fits_width"] and v["fits_height"]
        if not ok:
            failed = True
        size = f'{spec["width"]}"×{spec["height"]}"'
        grid = f'{spec["cols"]}×{spec["rows"]}'
        print(
            f"{code:8} {size:14} {grid:6} "
            f"{v['right_margin']:7.3f} {v['bottom_margin']:7.3f} "
            f"{'YES' if ok else 'NO'}"
        )
        if not ok:
            print(
                f"  ERROR: content {v['content_width']}\" × {v['content_height']}\" "
                f"exceeds letter page"
            )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
