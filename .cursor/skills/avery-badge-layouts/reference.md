# Avery Badge Layout Reference

## Authoritative lookup sources

| Source | URL | Best for |
|--------|-----|----------|
| MS Word Avery dimensions | https://helparchive.huntertur.net/document/23570 | Margins, pitch, grid (KB Q149153) |
| Avery templates | https://www.avery.com/templates/{code} | Label size, count per sheet |
| Avery products | https://www.avery.com/products/name-badges/{code} | Marketing dimensions, compatibility list |
| Avery margin help | https://www.avery.com/help/article/margin-settings-word-template | How to read Word Details dialog |

When Word and Avery disagree on label **size**, trust the **Avery product page**. When they disagree on **position on sheet**, trust **Word Side/Top Mar and Pitch**.

## Pitch → gap conversion

```
gap_horizontal = horiz_pitch - label_width   (only between columns)
gap_vertical   = vert_pitch   - label_height  (only between rows)
```

Example **5395** (Word row 5095/5395/5895):

- Wdth 3.375, Hgt 2.333, 2×4, Side 0.688, Top 0.583
- Horiz pitch 3.750 → gap_h = 3.750 − 3.375 = **0.375**
- Vert pitch 2.500 → gap_v = 2.500 − 2.333 = **0.167**

Example **5361** (right column):

- Wdth 3.250, Hgt 2.000, 1×3, Side **4.208**, Top 0.833
- Vert pitch 3.666 → gap_v = 3.666 − 2.000 = **1.666**
- Right margin = 8.5 − (4.208 + 3.25) = **1.042**

## PDF coordinate system (ReportLab)

Letter page: 8.5" × 11", portrait.

Badge **x** (from left):

```
x = margin_left + col * (badge_width + gap_horizontal)
```

Badge **y** (bottom-left corner, ReportLab origin bottom-left):

```
y = page_height - margin_top - (row + 1) * badge_height - row * gap_vertical
```

`col` and `row` are 0-based; index order is row-major (col varies fastest).

## Current registry (landscape dimensions)

| Code | Size (W×H) | Grid | margin_left | margin_top | gap_h | gap_v | Notes |
|------|------------|------|-------------|------------|-------|-------|-------|
| 5361 | 3.25×2.0 | 1×3 | 4.208 | 0.833 | 0 | 1.666 | Right column |
| 5390 | 3.5×2.25 | 2×4 | 0.75 | 1.167 | 0 | 0 | Word 5383 family |
| 5395 | 3.375×2.333 | 2×4 | 0.688 | 0.583 | 0.375 | 0.167 | |
| 5392 | 4.0×3.0 | 2×3 | 0.25 | 1.125 | 0 | 0 | Word 5384 family |
| 74459 | 4.0×3.0 | 2×3 | 0.25 | 1.125 | 0 | 0 | Same as 5392 |
| 8522 | 6.0×4.25 | 1×2 | 1.25 | 1.25 | 0 | 0 | |
| 5035 | 5.0×3.5 | 1×2 | 1.75 | 2.0 | 0 | 0 | Custom, not Avery |
| 8395 | 3.375×2.333 | 2×4 | 0.688 | 0.583 | 0.375 | 0.167 | Alias → 5395 |
| 5384 | 4.0×3.0 | 2×3 | 0.25 | 1.125 | 0 | 0 | Alias → 5392 |

Update this table when changing `AVERY_TEMPLATES`.

## Aliases

```python
AVERY_ALIASES = {
    "8395": "5395",
    "5384": "5392",
    "35392": "5392",
}
```

Add new aliases when Avery lists compatible template numbers on the product page. Point alias → canonical entry with full spec.

## Template families (share layout, different packaging)

| Layout | Avery template codes |
|--------|---------------------|
| 4×3 landscape, 2×3 | 5392, 5384, 74459, 35392, 5393, 74536, 74540, … |
| 3.375×2.333, 2×4 | 5395, 8395, 5095, 25395, … |
| 3.5×2.25, 2×4 | 5390, 5383, 74461, 74549 |
| 3.25×2.0, 1×3 right | 5361, 5362 |

Always verify with Word Details before aliasing a new SKU.

## Background assets

- Stored under `badge_background_templates/5392/` with fallback for other sizes.
- PDF generation resizes to `canvas_pixels(avery_code)` in `_prepare_background_image`.
- New size: optional dedicated PNG at exact canvas pixels improves quality; not required.

## Scaling pipeline (do not break)

1. Base SVG: 384×288 (5392)
2. `prepare_svg_for_avery()` → target canvas
3. `resolve_element_layout_for_canvas()` → scale saved layout
4. `apply_element_layout()` + square QR tags
5. PDF: uniform scale per badge cell; background fill exact cell size
