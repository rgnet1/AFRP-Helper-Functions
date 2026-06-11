# Badge Background Templates

Decorative backgrounds for Avery badge inserts. **One image = one badge face** (not a full sheet).

## Avery 5392 (landscape insert)

| Spec | Value |
|------|-------|
| Physical size | 4.0" wide × 3.0" tall |
| Minimum pixels (96 DPI) | **384 × 288 px** |
| Recommended print (300 DPI) | **1200 × 900 px** |
| Aspect ratio | **4:3** (required) |
| Formats | PNG (preferred) or JPEG |

## Safe zones

The shared layout overlay places content automatically. Keep these areas low-contrast or plain:

- **Top corners (y ~20):** club logo (left), AFRP logo (right)
- **Center band (y 100–190):** attendee name, club, table
- **Bottom-right (x 280–384, y 210–288):** QR code and member ID
- **Bottom-left:** sub-event list

Do **not** embed names, QR codes, or member IDs in the background image.

## Built-in backgrounds

Listed in `manifest.json` under `5392/`. Default is `white` (no file — solid white fill).

## Custom uploads

User uploads are stored in `5392/uploads/` and registered in `manifest.json` automatically.
