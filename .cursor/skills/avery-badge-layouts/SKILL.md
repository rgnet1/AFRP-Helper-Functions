---
name: avery-badge-layouts
description: Look up Avery US Letter name-badge dimensions, add or fix templates in AVERY_TEMPLATES, and validate PDF sheet alignment. Use when adding Avery sizes, fixing print misalignment, updating badge margins/gaps, or verifying label layout against official specs.
---

# Avery Badge Layouts

Guide for researching and implementing Avery label sheet specs in this app. Canonical registry: [utils/badges/badge_sizes.py](../../utils/badges/badge_sizes.py). PDF placement: [utils/badges/badge_generator.py](../../utils/badges/badge_generator.py).

## Orientation convention (critical)

This app uses **landscape badge dimensions** (width ≥ height) matching [static/svg/minimal_badge_landscape.svg](../../static/svg/minimal_badge_landscape.svg):

| Avery product page | App `width` × `height` |
|--------------------|-------------------------|
| 3" × 4" (portrait insert) | **4.0" × 3.0"** |
| 2-1/4" × 3-1/2" | **3.5" × 2.25"** |
| 2" × 3-1/4" (5361 card) | **3.25" × 2.0"** |

Canvas pixels = inches × **96** (`CANVAS_DPI`). Base design canvas is **5392** (384×288).

## How to look up specs

Use **two sources** and reconcile them:

1. **Microsoft Word Avery US Letter table** (most reliable for margins/pitch) — [KB Q149153](https://helparchive.huntertur.net/document/23570). In Word: Mailings → Labels → Options → Avery US Letter → product → **Details**.
2. **Avery.com** — product page + [templates/{code}](https://www.avery.com/templates) for label size and count per sheet.

Word table columns map to our fields:

| Word column | App field |
|-------------|-----------|
| Wdth | `width` (landscape) |
| Hgt | `height` (landscape) |
| Across | `cols` |
| Down | `rows` |
| Side Mar | `margin_left` |
| Top Mar | `margin_top` |
| Horiz Pitch | `gap_horizontal` = pitch − `width` (0 if cols = 1) |
| Vert Pitch | `gap_vertical` = pitch − `height` (0 if rows = 1) |

**Right-column layouts** (e.g. **5361**): Word “Side Mar” is a large **left** margin (~4.208"); labels sit on the right. Do not center unless the spec says symmetric margins.

**Template families**: Many SKUs share one layout (5392 ≡ 5384, 74459, 35392; 5395 ≡ 8395). Add aliases in `AVERY_ALIASES`, not duplicate specs.

Full lookup notes and current registry: [reference.md](reference.md).

## Add or update a template

### Checklist

```
- [ ] Look up Word + Avery product specs
- [ ] Convert to landscape width × height
- [ ] Compute gaps from pitch − label size
- [ ] Run validate_avery_sheet_layout (must fit 8.5" × 11")
- [ ] Add/update entry in AVERY_TEMPLATES
- [ ] Add AVERY_ALIASES if compatible SKU exists
- [ ] Update .cursor/rules/avery-layouts.mdc if base specs changed
- [ ] Test PDF: overlay plain-paper print on physical sheet
```

### Entry shape

Add to `AVERY_TEMPLATES` in `badge_sizes.py`:

```python
"XXXX": {
    "name": "Avery XXXX - …",
    "width": 3.375,       # inches, landscape
    "height": 2.333,
    "cols": 2,
    "rows": 4,
    "margin_left": 0.688,
    "margin_top": 0.583,
    "gap_horizontal": 0.375,
    "gap_vertical": 0.167,
    "size_category": "medium",   # small | medium | standard | large | xlarge
    "is_avery_standard": True,
    "dropdown": True,            # False = alias-only / internal
    "dropdown_order": 35,        # sort key in UI (small → large)
},
```

**Dropdown UI**: `list_dropdown_templates()` exposes templates with `dropdown: True` via `/api/avery-templates`. No HTML changes needed unless labels need custom copy.

**Backgrounds**: Uploads validate against `canvas_pixels(code)`. Fallback 5392 backgrounds are resized at PDF time for other sizes.

**Scaling**: SVG/layout scale from `BASE_CANVAS` (5392) automatically via `prepare_svg_for_avery()`. QR slots must stay square (`ensure_square_qr_image_tags`).

### Validate before committing

```bash
python .cursor/skills/avery-badge-layouts/scripts/validate_avery.py
# Or one code:
python .cursor/skills/avery-badge-layouts/scripts/validate_avery.py 5395
```

Or inline:

```python
from utils.badges.badge_sizes import AVERY_TEMPLATES, validate_avery_sheet_layout
v = validate_avery_sheet_layout(AVERY_TEMPLATES["5395"])
assert v["fits_width"] and v["fits_height"]
```

Expected: `content_width ≤ 8.5`, `content_height ≤ 11`. Note computed `right_margin` / `bottom_margin` — asymmetric top/bottom is normal (e.g. 5392: top 1.125", bottom ~0.875").

## Fix misalignment reports

1. Confirm user prints at **100% / Actual Size** (not Fit to Page).
2. Compare our spec vs Word Details for that product number.
3. Check **wrong template family** (user on 5395 sheet but template set to 5392).
4. Adjust `margin_left`, `margin_top`, `gap_*` in `AVERY_TEMPLATES` — never hack PDF scale.
5. Re-run validator; test one sheet on plain paper overlaid on Avery stock.

Common mistakes:

| Symptom | Likely cause |
|---------|----------------|
| Labels shifted right on 5361 | `margin_left` too small (should be ~4.208") |
| QR/logo stretched on smaller sizes | non-square QR after layout scale — see `ensure_square_qr_image_tags` |
| Green header doesn’t span badge | background not resized — `_prepare_background_image` |
| Right/bottom extra white | correct if spec has asymmetric margins |

## Files touched by Avery changes

| File | Role |
|------|------|
| `utils/badges/badge_sizes.py` | **Source of truth** — `AVERY_TEMPLATES`, aliases, validation, scaling |
| `utils/badges/badge_generator.py` | PDF grid: `margin_left + col * (width + gap_h)` |
| `utils/badges/background_templates.py` | Min upload size from `canvas_pixels` |
| `static/js/badge_scale.js` | Dev reference; bundled via `utils/badges/assets/` and `templates/partials/` |
| `.cursor/rules/avery-layouts.mdc` | Agent rule — keep in sync |

## Additional resources

- Current registry + Word pitch examples: [reference.md](reference.md)
- Validation script: [scripts/validate_avery.py](scripts/validate_avery.py)
