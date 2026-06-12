"""Badge background template catalog and upload validation."""

import json
import os
import re
import time
from io import BytesIO

from PIL import Image
from werkzeug.utils import secure_filename

from utils.badges.badge_sizes import canvas_pixels, resolve_avery_code

MANIFEST_FILENAME = "manifest.json"
FALLBACK_AVERY = "5392"
ASPECT_TOLERANCE = 0.01
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
THUMB_SIZE = (128, 96)
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def _manifest_path(root_dir):
    return os.path.join(root_dir, MANIFEST_FILENAME)


def load_manifest(root_dir):
    path = _manifest_path(root_dir)
    if not os.path.isfile(path):
        return {
            FALLBACK_AVERY: [
                {
                    "id": "white",
                    "name": "Plain White",
                    "builtin": True,
                    "file": None,
                    "thumbnail": "5392/thumbnails/white.png",
                }
            ]
        }
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_manifest(root_dir, manifest):
    with open(_manifest_path(root_dir), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")


def _entries_for_avery(manifest, avery_code):
    code = resolve_avery_code(avery_code)
    entries = manifest.get(code, [])
    if not entries and code != FALLBACK_AVERY:
        entries = manifest.get(FALLBACK_AVERY, [])
    return entries


def list_backgrounds(root_dir, avery_code=FALLBACK_AVERY):
    manifest = load_manifest(root_dir)
    entries = _entries_for_avery(manifest, avery_code)
    result = []
    for entry in entries:
        item = dict(entry)
        thumb = item.get("thumbnail")
        item["thumbnail_url"] = (
            f"/badge_background_templates/{thumb}" if thumb else None
        )
        result.append(item)
    return result


def find_background(root_dir, background_id, avery_code=FALLBACK_AVERY):
    if not background_id:
        background_id = "white"
    for entry in list_backgrounds(root_dir, avery_code):
        if entry["id"] == background_id:
            return entry
    return None


def resolve_background_path(root_dir, background_id, avery_code=FALLBACK_AVERY):
    """Return (is_builtin_white, absolute_image_path or None)."""
    entry = find_background(root_dir, background_id, avery_code)
    if not entry or entry.get("builtin") and not entry.get("file"):
        return True, None
    rel = entry.get("file")
    if not rel:
        return True, None
    path = os.path.join(root_dir, rel)
    if os.path.isfile(path):
        return False, os.path.abspath(path)
    return True, None


def _min_dimensions_for_avery(avery_code):
    w, h = canvas_pixels(avery_code)
    return w, h, w / h


def validate_background_image(file_storage, avery_code=FALLBACK_AVERY):
    """Validate uploaded image; return (pil_image, error_message)."""
    filename = secure_filename(file_storage.filename or "")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return None, "Only PNG and JPEG files are allowed"

    data = file_storage.read()
    if len(data) > MAX_UPLOAD_BYTES:
        return None, "File exceeds 5 MB limit"

    try:
        img = Image.open(BytesIO(data))
        img.load()
    except Exception:
        return None, "Invalid image file"

    min_w, min_h, aspect = _min_dimensions_for_avery(avery_code)
    w, h = img.size
    if w < min_w or h < min_h:
        return None, f"Image must be at least {min_w}×{min_h} px"

    ratio = w / h
    if abs(ratio - aspect) / aspect > ASPECT_TOLERANCE:
        return None, (
            f"Image aspect ratio must match badge size "
            f"({min_w}×{min_h}, ≈{aspect:.2f}:1)"
        )

    return img.convert("RGB"), None


def register_upload(root_dir, img, original_filename, avery_code=FALLBACK_AVERY):
    """Save uploaded background + thumbnail; append to manifest. Returns entry dict."""
    code = resolve_avery_code(avery_code)
    uploads_dir = os.path.join(root_dir, code, "uploads")
    thumbs_dir = os.path.join(root_dir, code, "thumbnails")
    os.makedirs(uploads_dir, exist_ok=True)
    os.makedirs(thumbs_dir, exist_ok=True)

    base = secure_filename(os.path.splitext(original_filename)[0]) or "background"
    base = re.sub(r"[^a-zA-Z0-9_-]", "_", base)[:40]
    slug = f"uploads/{int(time.time())}_{base}.png"
    rel_path = f"{code}/{slug}"
    thumb_rel = f"{code}/thumbnails/{os.path.basename(slug)}"

    full_path = os.path.join(root_dir, rel_path)
    thumb_path = os.path.join(root_dir, thumb_rel)
    img.save(full_path, format="PNG")
    cw, ch = canvas_pixels(code)
    thumb_w = max(64, min(128, cw // 3))
    thumb_h = max(48, min(96, ch // 3))
    img.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS).save(thumb_path, format="PNG")

    entry = {
        "id": slug.replace("/", "_").replace(".png", ""),
        "name": base.replace("_", " ").title(),
        "builtin": False,
        "file": rel_path,
        "thumbnail": thumb_rel,
    }

    manifest = load_manifest(root_dir)
    manifest.setdefault(code, []).append(entry)
    save_manifest(root_dir, manifest)
    entry["thumbnail_url"] = f"/badge_background_templates/{thumb_rel}"
    return entry
