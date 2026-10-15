"""Seating charts: one-time image layout, then live seat counts."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import List, Optional
import requests

RICH_TEXT_FILE = re.compile(r"msdyn_richtextfiles\(([0-9a-fA-F-]{36})\)")
TABLE_NUMBER = re.compile(r"\d+")
LAYOUT_VERSION = 14
_TABLE_NOTE = re.compile(r"will be removed after dinner", re.IGNORECASE)
_TABLE_PLACES = {"sf", "houston", "lexington", "phoenix", "brezeit"}
TABLE_KIND_LABELS = (
    ("general", "General"),
    ("afrp", "AFRP Reserved"),
    ("board", "Board"),
    ("sponsor", "Sponsor"),
    ("local", "Local club"),
    ("leadership", "Leadership"),
    ("vip", "VIP"),
    ("head", "Head"),
    ("guest", "Guest"),
    ("emergency", "Emergency"),
)


def table_kind(name: str) -> dict:
    """Stable type from the words after the dash, not the CRM role field.

    A city or club name wins over AFRP, so "AFRP/Phoenix Reserved" is a local
    club table. "Will be removed after dinner" is a note, not a type.
    """
    raw = (name or "").strip()
    suffix = " - ".join(part.strip() for part in raw.split(" - ")[1:]).strip()
    cleaned = _TABLE_NOTE.sub(" ", suffix)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
    tokens = set(re.findall(r"[a-z0-9]+", cleaned.lower()))
    if "head" in raw.lower():
        kind = "head"
    elif "emergency" in tokens:
        kind = "emergency"
    elif tokens & _TABLE_PLACES:
        kind = "local"
    elif "board" in tokens:
        kind = "board"
    elif "leadership" in tokens:
        kind = "leadership"
    elif tokens & {"sponsor", "sponsors"}:
        kind = "sponsor"
    elif "vip" in tokens:
        kind = "vip"
    elif "afrp" in tokens:
        kind = "afrp"
    elif tokens & {"guest", "guests"}:
        kind = "guest"
    elif cleaned:
        kind = "other"
    else:
        kind = "general"
    labels = dict(TABLE_KIND_LABELS)
    label = cleaned if kind == "other" else labels[kind]
    detail = suffix if suffix and suffix.lower() != label.lower() else ""
    return {"kind": kind, "kind_label": label, "kind_detail": detail}


def rich_text_file_id(html: str) -> str:
    match = RICH_TEXT_FILE.search(html or "")
    return match.group(1) if match else ""


def layout_dir() -> str:
    base = "/app/data" if os.environ.get("DOCKER_CONTAINER") else os.path.join(os.getcwd(), "data")
    path = os.path.join(base, "seating_layouts")
    os.makedirs(path, exist_ok=True)
    return path


def _raw_get(crm, path: str):
    url = f"{crm.crm_url}/api/data/v9.2/{path}"
    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {crm.access_token}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        },
        timeout=60,
    )
    if response.status_code >= 400:
        return b"", ""
    return response.content, response.headers.get("Content-Type") or "image/jpeg"


def chart_source(crm, event_id: str) -> dict:
    row = crm._make_request(
        f"campaigns({event_id})?$select=name,aha_imageofseatingchat,"
        "aha_imageofseatingarrangement_timestamp"
    )
    html = row.get("aha_imageofseatingchat") or ""
    file_id = rich_text_file_id(html)
    stamp = str(row.get("aha_imageofseatingarrangement_timestamp") or "")
    token = f"rich:{file_id}:{stamp}" if file_id else (f"image:{stamp}" if stamp else "")
    return {"name": row.get("name") or "", "file_id": file_id, "stamp": stamp, "token": token}


def image_pixels(content: bytes) -> int:
    from io import BytesIO
    from PIL import Image
    try:
        image = Image.open(BytesIO(content))
        return int(image.size[0]) * int(image.size[1])
    except Exception:
        return 0


def choose_chart(candidates) -> tuple:
    """Keep the largest picture. A 144px Dataverse thumbnail loses to the full file."""
    best = (b"", "")
    best_pixels = 0
    for content, content_type in candidates:
        if not content or len(content) <= 32:
            continue
        pixels = image_pixels(content)
        if pixels > best_pixels:
            best = (content, content_type or "image/jpeg")
            best_pixels = pixels
    return best


def download_chart(crm, event_id: str) -> tuple:
    source = chart_source(crm, event_id)
    paths = []
    if source["file_id"]:
        for column in ("msdyn_imageblob", "msdyn_fileblob"):
            paths.append(f"msdyn_richtextfiles({source['file_id']})/{column}/$value?size=full")
            paths.append(f"msdyn_richtextfiles({source['file_id']})/{column}/$value")
    paths.append(f"campaigns({event_id})/aha_imageofseatingarrangement/$value?size=full")
    paths.append(f"campaigns({event_id})/aha_imageofseatingarrangement/$value")
    candidates = [_raw_get(crm, path) for path in paths]
    content, content_type = choose_chart(candidates)
    token = source["token"] or (f"column:{source['stamp']}" if content else "")
    return content, content_type, token


def _read_labels(image_path: str) -> List[dict]:
    """Word boxes from one pass over the chart. Empty when tesseract is not installed."""
    if not shutil.which("tesseract"):
        return []
    try:
        result = subprocess.run(
            ["tesseract", image_path, "stdout", "--psm", "11", "tsv"],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    labels = []
    for line in (result.stdout or "").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        text = (parts[11] or "").strip()
        try:
            confidence = float(parts[10])
            left, top, box_w, box_h = (int(float(parts[index])) for index in (6, 7, 8, 9))
        except ValueError:
            continue
        if not text or confidence < 35 or box_w < 4 or box_h < 4:
            continue
        labels.append({"text": text, "x": left, "y": top, "w": box_w, "h": box_h})
    return labels


def match_tables(label: str, tables: List[dict]) -> Optional[dict]:
    numbers = [int(item) for item in TABLE_NUMBER.findall(label or "")]
    if not numbers:
        return None
    for number in numbers:
        for table in tables:
            table_numbers = [int(item) for item in TABLE_NUMBER.findall(table.get("name") or "")]
            if table.get("number") == number or number in table_numbers:
                return table
    return None


def _find_circles(image) -> List[tuple]:
    """Dark circular outlines, in pixels of this image."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    height, width = gray.shape[:2]
    min_radius = max(8, int(min(width, height) * 0.012))
    max_radius = max(min_radius + 2, int(min(width, height) * 0.08))
    found = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(min_radius * 2, 12),
        param1=100,
        param2=28,
        minRadius=min_radius,
        maxRadius=max_radius,
    )
    if found is None:
        return []
    return [(float(cx), float(cy), float(radius)) for cx, cy, radius in found[0]]


def _dedupe_circles(circles: List[tuple]) -> List[tuple]:
    kept = []
    for circle in circles:
        cx, cy, radius = circle
        if any((cx - other[0]) ** 2 + (cy - other[1]) ** 2 < (radius * 0.8) ** 2 for other in kept):
            continue
        kept.append(circle)
    return kept


def _read_number(image, cx: float, cy: float, radius: float, scale: float = 0.55):
    """Digits printed in the middle of one circle."""
    span = max(10, int(radius * scale))
    crop = image.crop((
        int(max(0, cx - span)),
        int(max(0, cy - span)),
        int(min(image.size[0], cx + span)),
        int(min(image.size[1], cy + span)),
    ))
    crop = crop.resize((max(span * 6, 80), max(span * 6, 80)))
    with tempfile.NamedTemporaryFile(suffix=".png") as handle:
        crop.save(handle.name)
        text = _ocr_crop(handle.name)
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits or digits == "0" or len(digits) > 4:
        return None
    return int(digits)


def _ocr_crop(image_path: str) -> str:
    if not shutil.which("tesseract"):
        return ""
    try:
        result = subprocess.run(
            [
                "tesseract", image_path, "stdout", "--psm", "7",
                "-c", "tessedit_char_whitelist=0123456789",
            ],
            capture_output=True, text=True, timeout=8, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout or ""


def _digit_groups(image) -> List[tuple]:
    """Numbers painted inside the tables, as (number, cx, cy, radius, confidence)."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    binary = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary)
    boxes = []
    for index in range(1, count):
        x, y, w, h, area = [int(value) for value in stats[index]]
        if 12 <= h <= 80 and 6 <= w <= 90 and 80 <= area <= 1400:
            boxes.append([x, y, w, h])
    boxes.sort(key=lambda item: (item[1], item[0]))
    merged = []
    for x, y, w, h in boxes:
        placed = False
        for other in merged:
            ox, oy, ow, oh = other
            same_row = abs((y + h / 2) - (oy + oh / 2)) < max(h, oh) * 0.65
            close = x <= ox + ow + max(6, h * 0.35) and ox <= x + w + max(6, oh * 0.35)
            if same_row and close:
                nx = min(x, ox)
                ny = min(y, oy)
                other[0] = nx
                other[1] = ny
                other[2] = max(x + w, ox + ow) - nx
                other[3] = max(y + h, oy + oh) - ny
                placed = True
                break
        if not placed:
            merged.append([x, y, w, h])
    found = []
    for x, y, w, h in merged:
        pad = max(3, int(h * 0.15))
        crop = image.crop((
            max(0, x - pad),
            max(0, y - pad),
            min(image.size[0], x + w + pad),
            min(image.size[1], y + h + pad),
        ))
        scale = 140 / max(crop.size)
        crop = crop.resize((max(20, int(crop.size[0] * scale)), max(20, int(crop.size[1] * scale))))
        number, confidence = _read_crop_number(crop)
        if number is None:
            continue
        found.append((
            number,
            x + w / 2,
            y + h / 2,
            max(h, w) * 1.15,
            confidence,
        ))
    return found


def _read_crop_number(crop):
    if not shutil.which("tesseract"):
        return None, 0
    with tempfile.NamedTemporaryFile(suffix=".png") as handle:
        crop.save(handle.name)
        try:
            result = subprocess.run(
                ["tesseract", handle.name, "stdout", "--psm", "7", "tsv"],
                capture_output=True, text=True, timeout=8, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None, 0
    best = None
    confidence = 0
    for line in (result.stdout or "").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        text = "".join(ch for ch in (parts[11] or "") if ch.isdigit())
        try:
            score = float(parts[10])
        except ValueError:
            continue
        if not text or text == "0" or len(text) > 3 or score < 25:
            continue
        if score >= confidence:
            best = int(text)
            confidence = score
    return best, confidence


def _table_circles(image, circles: List[tuple]) -> List[tuple]:
    """The radius band whose centers actually contain table numbers."""
    if len(circles) <= 8:
        return _dedupe_circles(circles)
    buckets = {}
    for circle in circles:
        buckets.setdefault(int(circle[2] // 6) * 6, []).append(circle)
    best = []
    best_score = -1
    for group in buckets.values():
        if len(group) < 4:
            continue
        step = max(1, len(group) // 4)
        sample = group[::step][:4]
        score = sum(1 for circle in sample if _read_number(image, *circle) is not None)
        if score > best_score:
            best = group
            best_score = score
    return _dedupe_circles(best or circles)


def _numbers_for(table: dict) -> List[int]:
    numbers = []
    raw = table.get("number")
    if isinstance(raw, bool):
        raw = None
    if isinstance(raw, (int, float)) and int(raw) > 0:
        numbers.append(int(raw))
    numbers.extend(int(item) for item in TABLE_NUMBER.findall(table.get("name") or ""))
    return numbers


def _chart_offset(found: List[int], tables: List[dict]) -> int:
    """Printed 1..N sometimes means tables 201.. when the room uses that block."""
    index = {}
    for table in tables:
        for number in _numbers_for(table):
            index.setdefault(number, table)
    if not found or not index:
        return 0
    offsets = {0}
    for chart_number in found[:8]:
        for table_number in index:
            offsets.add(table_number - chart_number)
    best_offset = 0
    best_score = -1
    for offset in sorted(offsets, key=lambda item: abs(item)):
        score = sum(1 for number in found if number + offset in index)
        if score > best_score:
            best_score = score
            best_offset = offset
    if best_score < max(2, len(found) // 2):
        return 0
    return best_offset


def _table_disks(image) -> List[tuple]:
    """One filled circle per table, in pixels. These are the chart's real positions."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    rgb = np.array(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    red = (rgb[:, :, 0] > 140) & (rgb[:, :, 1] < 140) & (rgb[:, :, 2] < 140)
    fill = (gray > 205) & (gray < 250)
    mask = np.where(red | fill, 255, 0).astype(np.uint8)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    found = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 400:
            continue
        peri = cv2.arcLength(contour, True) or 1
        if 4 * 3.1416 * area / (peri * peri) < 0.7:
            continue
        (cx, cy), radius = cv2.minEnclosingCircle(contour)
        if radius >= 18:
            found.append((float(cx), float(cy), float(radius)))
    if len(found) < 8:
        return []
    buckets = {}
    for disk in found:
        buckets.setdefault(int(disk[2] // 4) * 4, []).append(disk)
    return max(buckets.values(), key=len)


def _hough_tables(image, pitch: float) -> List[tuple]:
    """Circles the size of one table, separated by the gap measured from the numbers."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    if pitch < 20:
        return []
    gray = cv2.GaussianBlur(cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY), (5, 5), 0)
    found = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(pitch * 0.72, 24),
        param1=90,
        param2=28,
        minRadius=max(8, int(pitch * 0.28)),
        maxRadius=max(12, int(pitch * 0.5)),
    )
    if found is None:
        return []
    return [(float(cx), float(cy), float(radius)) for cx, cy, radius in found[0]]


def _cluster_axis(values: List[float], pitch: float) -> List[float]:
    grouped = []
    for value in sorted(values):
        if not grouped or value - grouped[-1][-1] > pitch * 0.45:
            grouped.append([value])
        else:
            grouped[-1].append(value)
    return [sum(group) / len(group) for group in grouped]


def _nearest_pitch(points: List[tuple]) -> float:
    gaps = _nearest_gaps(points)
    typical = _neighbor_gap(gaps)
    return typical or 40


def _spots_are_neighbors(left, right, pitch: float) -> bool:
    if not left or not right:
        return False
    gap = ((left["cx"] - right["cx"]) ** 2 + (left["cy"] - right["cy"]) ** 2) ** 0.5
    return gap <= pitch * 1.6


def _label_circles(circles: List[tuple], digits: List[tuple]) -> List[dict]:
    """Keep every circle. A printed number is attached to the circle it sits in."""
    spots = [{
        "cx": cx, "cy": cy, "radius": radius, "number": None, "distance": None,
    } for cx, cy, radius in circles]
    for number, dx, dy, _radius, _confidence in digits:
        best = None
        best_distance = None
        for index, spot in enumerate(spots):
            distance = ((spot["cx"] - dx) ** 2 + (spot["cy"] - dy) ** 2) ** 0.5
            if distance > max(spot["radius"], 12) * 0.95:
                continue
            if best_distance is None or distance < best_distance:
                best = index
                best_distance = distance
        if best is None:
            continue
        current = spots[best]["distance"]
        if current is None or best_distance < current:
            spots[best]["number"] = number
            spots[best]["distance"] = best_distance
    for spot in spots:
        spot.pop("distance", None)
    return spots


def _drop_touching_circles(spots: List[dict], pitch: float) -> List[dict]:
    """Two centers on top of each other are one table. Keep the one with a number."""
    kept = []
    for spot in sorted(spots, key=lambda item: (item["cy"], item["cx"])):
        twin = None
        for other in kept:
            distance = ((spot["cx"] - other["cx"]) ** 2 + (spot["cy"] - other["cy"]) ** 2) ** 0.5
            if distance < pitch * 0.45:
                twin = other
                break
        if twin is None:
            kept.append(spot)
            continue

        def _rank(item):
            number = item.get("number") or 0
            return (number >= 10, number > 0)

        if _rank(spot) > _rank(twin):
            kept[kept.index(twin)] = spot
    return kept


def _row_runs(spots: List[dict], pitch: float) -> List[list]:
    rows = []
    for spot in sorted(spots, key=lambda item: (item["cy"], item["cx"])):
        if not rows or abs(spot["cy"] - rows[-1][0]["cy"]) > pitch * 0.45:
            rows.append([spot])
        else:
            rows[-1].append(spot)
    runs = []
    for row in rows:
        row.sort(key=lambda spot: spot["cx"])
        run = []
        for spot in row:
            if run and spot["cx"] - run[-1]["cx"] > pitch * 1.6:
                runs.append(run)
                run = []
            run.append(spot)
        if run:
            runs.append(run)
    return runs


def _projection(piece: List[dict], step: int, claimed: set, ceiling: int):
    """The arithmetic sequence, anchored on the readings that agree with it."""
    known = [(index, piece[index]["number"]) for index in range(len(piece)) if piece[index].get("number")]
    if len(piece) == 1:
        number = piece[0].get("number")
        if not number or number in claimed and piece[0].get("number") != number:
            return None
        return [number]
    if len(known) < 1:
        return None
    best = None
    best_key = None
    for ref_index, ref_number in known:
        expected = [ref_number + step * (index - ref_index) for index in range(len(piece))]
        if any(number <= 0 or number > ceiling for number in expected):
            continue
        if len(set(expected)) != len(expected):
            continue
        if any(number in claimed and piece[index].get("number") != number for index, number in enumerate(expected)):
            continue
        full_hits = full_miss = exact_small = unit_hits = small_miss = fills = 0
        for index, spot in enumerate(piece):
            number = spot.get("number")
            got = expected[index]
            if not number:
                fills += 1
            elif number == got and number >= 10:
                full_hits += 1
            elif number == got:
                exact_small += 1
            elif number >= 10:
                full_miss += 1
            elif got >= 10 and number == got % 10:
                unit_hits += 1
            else:
                small_miss += 1
        support = full_hits + exact_small + unit_hits
        if support < 2 or full_hits + exact_small < 1:
            continue
        if full_miss > full_hits:
            continue
        key = (full_hits - full_miss, full_hits + exact_small, unit_hits, fills, -small_miss)
        if best_key is None or key > best_key:
            best_key = key
            best = expected
    return best


def _piece_score(piece: List[dict], expected: List[int]) -> int:
    score = 0
    for spot, got in zip(piece, expected):
        number = spot.get("number")
        if not number:
            score += 2
        elif number == got and number >= 10:
            score += 6
        elif number == got:
            score += 5
        elif number < 10 and got >= 10 and number == got % 10:
            score += 4
        elif number >= 10:
            score -= 5
        else:
            score -= 1
    return score


def _best_piece(piece: List[dict], claimed: set, ceiling: int):
    best = None
    best_score = None
    for step in (1, -1, 2, -2):
        expected = _projection(piece, step, claimed, ceiling)
        if not expected:
            continue
        score = _piece_score(piece, expected)
        if best_score is None or score > best_score:
            best = expected
            best_score = score
    return best, best_score


def _majority_odd(numbers: List[int]):
    odd = sum(number % 2 for number in numbers)
    if odd == len(numbers) - odd:
        return None
    return odd > len(numbers) / 2


def _assign_run(run: List[dict], claimed: set, ceiling: int):
    """One straight run. Odds and evens split only when that scores higher."""
    best = None
    best_score = None
    whole, whole_score = _best_piece(run, claimed, ceiling)
    if whole is not None:
        best = whole
        best_score = whole_score + 8
    for cut in range(2, len(run) - 1):
        left, left_score = _best_piece(run[:cut], claimed, ceiling)
        if not left:
            continue
        right, right_score = _best_piece(run[cut:], set(claimed) | set(left), ceiling)
        if not right or set(left) & set(right):
            continue
        left_odd = _majority_odd(left)
        right_odd = _majority_odd(right)
        if left_odd is not None and right_odd is not None and left_odd == right_odd:
            continue
        score = left_score + right_score
        if best_score is None or score > best_score:
            best = left + right
            best_score = score
    if not best:
        return
    for spot, number in zip(run, best):
        spot["number"] = number
        claimed.add(number)


def _anchor_numbers(run: List[dict]) -> set:
    """Two-digit readings that already step by one or two. Those seats are taken."""
    known = [(index, run[index]["number"]) for index in range(len(run)) if (run[index].get("number") or 0) >= 10]
    anchors = set()
    for left in range(len(known)):
        for right in range(left + 1, len(known)):
            span = known[right][0] - known[left][0]
            diff = known[right][1] - known[left][1]
            if span and diff % span == 0 and diff // span in (1, -1, 2, -2):
                anchors.add(known[left][1])
                anchors.add(known[right][1])
    return anchors


def _fill_runs(spots: List[dict], valid: Optional[set] = None) -> List[dict]:
    """Put each reading on its own circle, then fill only the blank ones.

    A wide gap, such as the dance floor or the head table, starts a new run.
    A one-digit read is the units digit of the two-digit number the row is
    already counting. A read that is not a table number is ignored.
    """
    if len(spots) < 3:
        return spots
    for spot in spots:
        if spot.get("number") and (spot["number"] > 110 or spot["number"] <= 0):
            spot["number"] = None
    pitch = _nearest_pitch([(float(spot["cx"]), float(spot["cy"])) for spot in spots])
    order = {id(spot): index for index, spot in enumerate(spots)}
    kept = _drop_touching_circles(spots, pitch)
    runs = _row_runs(kept, pitch)
    ceiling = 110
    if valid:
        positive = [number for number in valid if number > 0]
        if positive:
            ceiling = max(positive)
    claimed = set()
    for run in runs:
        claimed |= _anchor_numbers(run)
    runs.sort(key=lambda run: -sum(1 for spot in run if (spot.get("number") or 0) >= 10))
    for run in runs:
        _assign_run(run, claimed, ceiling)
    return sorted(kept, key=lambda spot: order.get(id(spot), 0))


def _repair_odd_even_seams(spots: List[dict]) -> None:
    """101 follows 99, and 17 comes before 19, even when the read number was garbage."""
    if len(spots) < 3:
        return
    pitch = _nearest_pitch([(float(spot["cx"]), float(spot["cy"])) for spot in spots])
    used = {spot["number"] for spot in spots if spot.get("number")}
    rows = []
    for spot in sorted(spots, key=lambda item: (item["cy"], item["cx"])):
        if not rows or abs(spot["cy"] - rows[-1][0]["cy"]) > pitch * 0.45:
            rows.append([spot])
        else:
            rows[-1].append(spot)
    for row in rows:
        row.sort(key=lambda spot: spot["cx"])
        for index, spot in enumerate(row):
            number = spot.get("number")
            if not number or number > 110:
                continue
            if index + 1 < len(row) and abs(row[index + 1]["cx"] - spot["cx"]) <= pitch * 2.2:
                nxt = row[index + 1]
                candidate = number + 2
                if (not nxt.get("number") or nxt["number"] > 110) and candidate not in used and candidate % 2 == number % 2:
                    nxt["number"] = candidate
                    used.add(candidate)
            if index and abs(spot["cx"] - row[index - 1]["cx"]) <= pitch * 2.2:
                prev = row[index - 1]
                candidate = number - 2
                if (
                    candidate > 0 and (not prev.get("number") or prev["number"] > 110)
                    and candidate not in used and candidate % 2 == number % 2
                ):
                    prev["number"] = candidate
                    used.add(candidate)


def _point_in_block(x, y, block) -> bool:
    return block["x"] <= x <= block["x"] + block["w"] and block["y"] <= y <= block["y"] + block["h"]


def _add_missing_edge_seats(spots: List[dict], blocks: List[dict], width: int, height: int) -> List[dict]:
    """Put back a seat that sits just outside the dance floor, such as 17 or 26."""
    if len(spots) < 3:
        return spots
    pitch = _nearest_pitch([(float(spot["cx"]), float(spot["cy"])) for spot in spots])
    used = {spot["number"] for spot in spots if spot.get("number")}
    rows = []
    for spot in sorted(spots, key=lambda item: (item["cy"], item["cx"])):
        if not rows or abs(spot["cy"] - rows[-1][0]["cy"]) > pitch * 0.45:
            rows.append([spot])
        else:
            rows[-1].append(spot)
    added = []
    for row in rows:
        row.sort(key=lambda spot: spot["cx"])
        runs = [[]]
        for spot in row:
            if runs[-1] and spot["cx"] - runs[-1][-1]["cx"] > pitch * 1.6:
                runs.append([])
            runs[-1].append(spot)
        for run in runs:
            known = [(index, run[index]["number"]) for index in range(len(run)) if run[index].get("number")]
            if len(known) < 2:
                continue
            span = known[-1][0] - known[0][0]
            if not span or (known[-1][1] - known[0][1]) % span != 0:
                continue
            step = (known[-1][1] - known[0][1]) // span
            if step not in (1, -1, 2, -2):
                continue
            radius = run[0]["radius"]
            for number, x in (
                (run[0]["number"] - step, run[0]["cx"] - pitch),
                (run[-1]["number"] + step, run[-1]["cx"] + pitch),
            ):
                y = run[0]["cy"]
                if number <= 0 or number in used or not (radius < x < width - radius):
                    continue
                if any(_point_in_block(x, y, block) for block in blocks):
                    continue
                nearby = [
                    other for other in spots + added
                    if abs(x - other["cx"]) < pitch * 0.6 and abs(y - other["cy"]) < pitch * 0.6
                ]
                if nearby:
                    other = nearby[0]
                    if other.get("number") and other["number"] <= 110:
                        continue
                    if other.get("number"):
                        used.discard(other["number"])
                    other["number"] = number
                    used.add(number)
                    continue
                added.append({"cx": x, "cy": y, "radius": radius, "number": number})
                used.add(number)
        for index in range(len(row) - 1):
            left, right = row[index], row[index + 1]
            gap = right["cx"] - left["cx"]
            if not (pitch * 1.5 <= gap <= pitch * 2.6):
                continue
            if not left.get("number") or not right.get("number"):
                continue
            choices = []
            previous = row[index - 1] if index else None
            nxt = row[index + 2] if index + 2 < len(row) else None
            if previous and previous.get("number") and abs(left["cx"] - previous["cx"]) <= pitch * 1.4:
                step = left["number"] - previous["number"]
                if step in (1, -1, 2, -2):
                    choices.append(left["number"] + step)
            if nxt and nxt.get("number") and abs(nxt["cx"] - right["cx"]) <= pitch * 1.4:
                step = nxt["number"] - right["number"]
                if step in (1, -1, 2, -2):
                    choices.append(right["number"] - step)
            pick = next((item for item in choices if item > 0 and item not in used), None)
            if pick is None:
                continue
            x = (left["cx"] + right["cx"]) / 2
            y = left["cy"]
            if any(_point_in_block(x, y, block) for block in blocks):
                continue
            added.append({"cx": x, "cy": y, "radius": left["radius"], "number": pick})
            used.add(pick)
    return spots + added


def _room_blocks(image) -> List[dict]:
    """Large light rectangles. These are the dance floor, or a head table."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    mask = np.where((gray > 210) & (gray < 248), 255, 0).astype(np.uint8)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blocks = []
    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, w, h = cv2.boundingRect(contour)
        if area < 20000 or w < 80 or h < 80:
            continue
        blocks.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h), "area": int(area)})
    return blocks


def _head_table(tables: List[dict]):
    for table in tables:
        if "head" in (table.get("name") or "").lower():
            return table
    return None


def _block_text(image, block: dict) -> str:
    """Words printed inside one grey rectangle, such as Head table or Stage."""
    if not shutil.which("tesseract"):
        return ""
    crop = image.crop((
        block["x"],
        block["y"],
        min(image.size[0], block["x"] + block["w"]),
        min(image.size[1], block["y"] + block["h"]),
    ))
    crop = crop.resize((max(crop.size[0] * 2, 40), max(crop.size[1] * 2, 40)))
    with tempfile.NamedTemporaryFile(suffix=".png") as handle:
        crop.save(handle.name)
        try:
            result = subprocess.run(
                ["tesseract", handle.name, "stdout", "--psm", "6"],
                capture_output=True, text=True, timeout=8, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
    return (result.stdout or "").lower()


def _words_for_block(block: dict, text: str, labels: List[dict]) -> str:
    parts = [text or ""]
    for label in labels:
        cx = label["x"] + label["w"] / 2
        cy = label["y"] + label["h"] / 2
        if _point_in_block(cx, cy, block):
            parts.append(label.get("text") or "")
    return " ".join(parts).lower()


def _classify_blocks(blocks: List[dict], texts: List[str], labels: List[dict]):
    """A rectangle is the head table only when it says so. The others are the stage."""
    head = None
    stages = []
    dances = []
    for block, text in zip(blocks, texts):
        words = _words_for_block(block, text, labels)
        if "head" in words or re.search(r"\btable\b", words):
            if head is None or block["w"] > head["w"]:
                if head is not None:
                    stages.append(head)
                head = block
            else:
                stages.append(block)
        elif "dance" in words:
            dances.append(block)
        else:
            stages.append(block)
    return head, stages, dances


def _one_row_height(spots: List[dict], stage_h: float) -> int:
    """Height of one table row. Short, so a head table is not another stage."""
    numbered = [spot for spot in spots if spot.get("number")]
    radii = sorted(spot["radius"] for spot in numbered if spot.get("radius"))
    radius = radii[len(radii) // 2] if radii else 0
    ys = sorted(spot["cy"] for spot in numbered)
    floor_gap = max(18, radius * 0.8) if radius else 18
    ceiling = radius * 5 if radius else 240
    gaps = [b - a for a, b in zip(ys, ys[1:]) if floor_gap <= b - a <= ceiling]
    if gaps:
        height = sorted(gaps)[len(gaps) // 2] * 0.62
    elif radius:
        height = radius * 2.2
    else:
        height = 90
    cap = stage_h * 0.45 if stage_h else height
    return int(max(64, min(height, cap)))


def _head_in_front(stages: List[dict], spots: List[dict], width: int, height: int):
    """A head table the picture does not draw, one row in front of the stage.

    Image y grows downward, so the front of the room is the bottom. The new
    rectangle starts past the bottom edge of the front grey box. It may extend
    below the picture; that is stored as a percentage over 100.
    """
    numbered = [spot for spot in spots if spot.get("number")]
    front = sorted(numbered, key=lambda spot: spot["number"])[:8]
    if stages:
        # Front of the room is the bottom. On Grand Banquet that box is also
        # the one beside tables 1–8, so the head row sits in front of it.
        stage = max(stages, key=lambda block: block["y"] + block["h"])
        cx = stage["x"] + stage["w"] / 2
        rect_h = _one_row_height(spots, stage["h"])
        rect_w = max(160, stage["w"] * 0.86)
        gap = max(8, int(rect_h * 0.16))
        top = stage["y"] + stage["h"] + gap
    elif front:
        cx = sum(spot["cx"] for spot in front) / len(front)
        span = max(spot["cx"] for spot in front) - min(spot["cx"] for spot in front)
        rect_w = max(160, span * 0.45)
        rect_h = _one_row_height(spots, rect_w)
        top = max(spot["cy"] for spot in front) + max(8, int(rect_h * 0.16))
    else:
        return None
    if numbered:
        lowest = max(spot["cy"] for spot in numbered)
        if top <= lowest:
            top = lowest + 1
    rect_w = min(rect_w, width)
    left = cx - rect_w / 2
    if left < 0:
        left = 0
    if left + rect_w > width:
        left = max(0, width - rect_w)
    rect = {
        "x": int(round(left)),
        "y": int(round(top)),
        "w": int(round(rect_w)),
        "h": int(round(rect_h)),
    }
    for _ in range(8):
        blocked = [
            spot for spot in numbered
            if rect["x"] <= spot["cx"] <= rect["x"] + rect["w"]
            and rect["y"] <= spot["cy"] <= rect["y"] + rect["h"]
        ]
        if not blocked:
            break
        rect["y"] = int(max(spot["cy"] for spot in blocked) + 1)
    return rect


def _split_odd_even(run: List[dict]) -> List[list]:
    """Grand Banquet puts odds on one side of the floor and evens on the other."""
    if len(run) < 6:
        return [run]
    best = None
    best_gap = 0
    for cut in range(2, len(run) - 1):
        left = [spot["number"] for spot in run[:cut] if spot.get("number")]
        right = [spot["number"] for spot in run[cut:] if spot.get("number")]
        if len(left) < 2 or len(right) < 2:
            continue
        left_odd = sum(number % 2 for number in left) / len(left)
        right_odd = sum(number % 2 for number in right) / len(right)
        if not (
            (left_odd >= 0.75 and right_odd <= 0.25)
            or (left_odd <= 0.25 and right_odd >= 0.75)
        ):
            continue
        gap = abs(left_odd - right_odd)
        if gap > best_gap:
            best = cut
            best_gap = gap
    if best is None:
        return [run]
    return [run[:best], run[best:]]


def infer_table_numbers(spots: List[dict]) -> List[dict]:
    """Fill unread circles from the step between the numbers around them.

    Spots keep the centers found on the picture. A circle read as both 5 and 9
    keeps the number that continues the row, and the other number stays free
    for an empty circle.
    """
    if len(spots) < 3:
        return spots
    points = [(float(spot["cx"]), float(spot["cy"])) for spot in spots]
    pitch = _nearest_pitch(points)
    columns = _cluster_axis([point[0] for point in points], pitch)
    rows = _cluster_axis([point[1] for point in points], pitch)
    grid = [[None for _ in columns] for _ in rows]
    cells = [[None for _ in columns] for _ in rows]
    for spot in spots:
        col = min(range(len(columns)), key=lambda index: abs(columns[index] - spot["cx"]))
        row = min(range(len(rows)), key=lambda index: abs(rows[index] - spot["cy"]))
        cells[row][col] = spot
        number = spot.get("number")
        if number and grid[row][col] is None:
            grid[row][col] = number
    height = len(rows)
    width = len(columns)

    def _row_step(values):
        known = [(col, values[col]) for col in range(len(values)) if values[col]]
        if len(known) < 2:
            return None
        steps = []
        for (left, first), (right, second) in zip(known, known[1:]):
            span = right - left
            if cells[row][left] and cells[row][right]:
                gap = (
                    (cells[row][left]["cx"] - cells[row][right]["cx"]) ** 2
                    + (cells[row][left]["cy"] - cells[row][right]["cy"]) ** 2
                ) ** 0.5
                if gap > max(span, 1) * pitch * 1.6:
                    continue
            if span and (second - first) % span == 0:
                steps.append((second - first) // span)
        if not steps:
            return None
        choice = max(set(steps), key=steps.count)
        if steps.count(choice) >= 2:
            return choice
        start, end = known[0], known[-1]
        span = end[0] - start[0]
        if span and (end[1] - start[1]) % span == 0:
            return (end[1] - start[1]) // span
        return choice

    for row in range(height):
        step = _row_step(grid[row])
        if step is None:
            continue
        for col in range(width):
            number = grid[row][col]
            if not number:
                continue
            votes = []
            if col and grid[row][col - 1] and _spots_are_neighbors(cells[row][col], cells[row][col - 1], pitch):
                votes.append(grid[row][col - 1] + step)
            if col + 1 < width and grid[row][col + 1] and _spots_are_neighbors(cells[row][col], cells[row][col + 1], pitch):
                votes.append(grid[row][col + 1] - step)
            if len(votes) >= 2 and len(set(votes)) == 1 and votes[0] != number:
                grid[row][col] = None
    counts = {}
    for line in grid:
        for number in line:
            if number:
                counts[number] = counts.get(number, 0) + 1
    for row in range(height):
        step = _row_step(grid[row])
        if step is None:
            continue
        for col in range(width):
            number = grid[row][col]
            if not number or counts.get(number, 0) < 2:
                continue
            expected = None
            if col and grid[row][col - 1] and _spots_are_neighbors(cells[row][col], cells[row][col - 1], pitch):
                expected = grid[row][col - 1] + step
            elif (
                col + 1 < width and grid[row][col + 1]
                and _spots_are_neighbors(cells[row][col], cells[row][col + 1], pitch)
            ):
                expected = grid[row][col + 1] - step
            if expected and expected != number:
                grid[row][col] = None
                counts[number] -= 1
    changed = True
    while changed:
        changed = False
        for row in range(height):
            step = _row_step(grid[row])
            if step is None:
                continue
            used = {value for line in grid for value in line if value}
            for col in range(width):
                if cells[row][col] is None or grid[row][col]:
                    continue
                guesses = []
                if col and grid[row][col - 1] and _spots_are_neighbors(cells[row][col], cells[row][col - 1], pitch):
                    guesses.append(grid[row][col - 1] + step)
                if col + 1 < width and grid[row][col + 1] and _spots_are_neighbors(cells[row][col], cells[row][col + 1], pitch):
                    guesses.append(grid[row][col + 1] - step)
                if guesses and len(set(guesses)) == 1 and guesses[0] > 0 and guesses[0] not in used:
                    grid[row][col] = guesses[0]
                    changed = True
    filled = []
    for row in range(height):
        for col in range(width):
            spot = cells[row][col]
            if spot is None:
                continue
            copy = dict(spot)
            if grid[row][col]:
                copy["number"] = grid[row][col]
            filled.append(copy)
    return filled


def _working_image(image):
    from PIL import Image
    width, height = image.size
    longest = max(width, height)
    if longest < 1600:
        scale = 1600 / longest
    elif longest > 2200:
        scale = 2200 / longest
    else:
        return image
    return image.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)


def convert_chart(image_bytes: bytes, tables: List[dict]) -> dict:
    """Find numbered circles and save their centers. The picture is not kept."""
    from io import BytesIO
    from PIL import Image

    image = _working_image(Image.open(BytesIO(image_bytes)).convert("RGB"))
    width, height = image.size
    digits = _digit_groups(image)
    disks = _table_disks(image)
    unique_digits = len({item[0] for item in digits})
    if len(disks) >= 8 and (unique_digits < 8 or len(disks) >= unique_digits * 0.7):
        spots = _label_circles(disks, digits)
        for spot in spots:
            if spot["number"] is None:
                spot["number"] = _read_number(image, spot["cx"], spot["cy"], spot["radius"])
    else:
        points = [(item[1], item[2]) for item in digits]
        pitch = _nearest_pitch(points) if len(points) >= 3 else 80
        circles = _hough_tables(image, pitch)
        half = _hough_tables(image, pitch * 0.55)
        if len(half) > len(circles) or (
            len(half) == len(circles) and half and circles
            and sorted(item[2] for item in half)[len(half) // 2]
            < sorted(item[2] for item in circles)[len(circles) // 2]
        ):
            circles = half
        spots = _label_circles(circles, digits) if len(circles) >= 8 else [
            {"cx": cx, "cy": cy, "radius": radius, "number": number}
            for number, cx, cy, radius, _confidence in digits
        ]
        for spot in spots:
            if spot.get("number") is None and spot.get("radius"):
                spot["number"] = _read_number(image, spot["cx"], spot["cy"], spot["radius"], 0.85)
    valid = {number for table in tables for number in _numbers_for(table)}
    spots = _fill_runs(spots, valid)
    blocks = _room_blocks(image)
    with tempfile.NamedTemporaryFile(suffix=".png") as handle:
        image.save(handle.name)
        labels = _read_labels(handle.name)
    texts = [_block_text(image, block) for block in blocks]
    head_block, stages, dances = _classify_blocks(blocks, texts, labels)
    head = _head_table(tables)
    if head and head_block is None:
        head_block = _head_in_front(stages or dances, spots, width, height)
    spots = _add_missing_edge_seats(spots, stages + dances, width, height)
    found = []
    seen_numbers = set()
    for spot in spots:
        number = spot.get("number")
        if not number or number in seen_numbers:
            continue
        seen_numbers.add(number)
        found.append((number, spot["cx"], spot["cy"], spot["radius"]))
    offset = _chart_offset([number for number, *_rest in found], tables)
    by_number = {}
    for table in tables:
        for number in _numbers_for(table):
            by_number.setdefault(number, table)
    radii = [radius for _number, _cx, _cy, radius in found if radius]
    shared_px = sorted(radii)[len(radii) // 2] if radii else 0
    placed = []
    used = set()
    for number, cx, cy, _radius in found:
        table = by_number.get(number + offset)
        if not table or table["id"] in used:
            continue
        used.add(table["id"])
        placed.append({
            "id": table["id"],
            "cx": round(100 * cx / width, 2),
            "cy": round(100 * cy / height, 2),
            "r": round(100 * shared_px / width, 2) if shared_px else 0,
        })
    if placed and not placed[0]["r"]:
        shared = same_table_radius(placed, width, height)
        for row in placed:
            row["r"] = shared
    landmarks = []
    for block in dances:
        landmarks.append({
            "kind": "dance",
            "label": "Dance floor",
            "x": round(100 * block["x"] / width, 2),
            "y": round(100 * block["y"] / height, 2),
            "w": round(100 * block["w"] / width, 2),
            "h": round(100 * block["h"] / height, 2),
        })
    for block in stages:
        landmarks.append({
            "kind": "stage",
            "label": "Stage",
            "x": round(100 * block["x"] / width, 2),
            "y": round(100 * block["y"] / height, 2),
            "w": round(100 * block["w"] / width, 2),
            "h": round(100 * block["h"] / height, 2),
        })
    if head and head_block and head["id"] not in used:
        placed.append({
            "id": head["id"],
            "shape": "rect",
            "cx": round(100 * (head_block["x"] + head_block["w"] / 2) / width, 2),
            "cy": round(100 * (head_block["y"] + head_block["h"] / 2) / height, 2),
            "w": round(100 * head_block["w"] / width, 2),
            "h": round(100 * head_block["h"] / height, 2),
            "r": 0,
        })
        used.add(head["id"])
    for label in labels:
        if "stage" not in (label.get("text") or "").lower():
            continue
        if any(_point_in_block(label["x"], label["y"], block) for block in stages):
            continue
        landmarks.append({
            "label": "Stage",
            "x": round(100 * label["x"] / width, 2),
            "y": round(100 * label["y"] / height, 2),
            "w": round(100 * label["w"] / width, 2),
            "h": round(100 * label["h"] / height, 2),
        })
        break
    return {
        "version": LAYOUT_VERSION,
        "width": width,
        "height": height,
        "tables": placed,
        "landmarks": landmarks,
    }


def _read_layout(event_id: str) -> Optional[dict]:
    path = os.path.join(layout_dir(), f"{event_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def saved_layout(event_id: str, token: str) -> Optional[dict]:
    data = _read_layout(event_id)
    if not data or data.get("version") != LAYOUT_VERSION or data.get("token") != token:
        return None
    return data


def store_layout(event_id: str, token: str, layout: dict, image_bytes: bytes = b"", content_type: str = "") -> dict:
    folder = layout_dir()
    payload = dict(layout)
    payload["version"] = LAYOUT_VERSION
    payload["token"] = token
    with open(os.path.join(folder, f"{event_id}.json"), "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    for suffix in (".img", ".type"):
        leftover = os.path.join(folder, f"{event_id}{suffix}")
        if os.path.exists(leftover):
            os.remove(leftover)
    return payload


def ensure_layout(crm, event_id: str, tables: List[dict]) -> dict:
    """Use the saved floor plan. The picture is read again only when that file is missing."""
    existing = _read_layout(event_id)
    if existing and existing.get("version") == LAYOUT_VERSION:
        return existing
    source = chart_source(crm, event_id)
    if source["token"]:
        existing = saved_layout(event_id, source["token"])
        if existing:
            return existing
    content, _content_type, token = download_chart(crm, event_id)
    if not content:
        return {"version": LAYOUT_VERSION, "width": 0, "height": 0, "tables": [], "landmarks": [], "token": ""}
    existing = saved_layout(event_id, token)
    if existing:
        return existing
    layout = convert_chart(content, tables)
    return store_layout(event_id, token, layout, content, _content_type)


def _assigned_campaigns(desk, campaign_ids) -> List[dict]:
    """Load assigned campaigns with no Open-status filter.

    Coordinators keep seating for their event after it leaves the open list.
    """
    ids = []
    for item in campaign_ids or []:
        text = (item or "").strip()
        if text and text.lower() not in {existing.lower() for existing in ids}:
            ids.append(text)
    found = {}
    for start in range(0, len(ids), 20):
        chunk = ids[start:start + 20]
        filt = " or ".join(f"campaignid eq {campaign_id}" for campaign_id in chunk)
        rows = desk.crm._make_request(
            "campaigns?$select=campaignid,name"
            f"&$filter={requests.utils.quote(filt)}"
        ).get("value") or []
        for row in rows:
            campaign_id = (row.get("campaignid") or "").strip()
            if campaign_id:
                found[campaign_id.lower()] = {
                    "id": campaign_id,
                    "name": row.get("name") or "Event",
                }
    return [found[campaign_id.lower()] for campaign_id in ids if campaign_id.lower() in found]


def events_with_tables(desk, user) -> List[dict]:
    """Events the user may open, each with the sub-events that have tables.

    Admins see open campaigns. Event coordinators see only their assigned
    event, including when that campaign is not Open.
    """
    from utils.auth.campaign_access import user_campaign_is_restricted

    rows = desk.crm._paginate(
        "aha_seatingtables?$select=_aha_event_value&$filter=statecode eq 0"
    )
    with_tables = {
        (row.get("_aha_event_value") or "").strip().lower()
        for row in rows
        if (row.get("_aha_event_value") or "").strip()
    }
    if user_campaign_is_restricted(user):
        parents = _assigned_campaigns(desk, user.allowed_campaign_ids())
    else:
        parents = desk.parent_events_for(user)
    grouped = []
    for parent in parents:
        parent_id = (parent.get("id") or "").strip()
        if not parent_id:
            continue
        children = []
        if parent_id.lower() in with_tables:
            children.append({"id": parent_id, "name": parent.get("name") or "Event"})
        for sub in desk.sub_events(parent_id):
            sub_id = (sub.get("id") or "").strip()
            if sub_id and sub_id.lower() in with_tables and sub_id.lower() != parent_id.lower():
                children.append({"id": sub_id, "name": sub.get("name") or "Event"})
        if not children:
            continue
        grouped.append({
            "id": parent_id,
            "name": parent.get("name") or "Event",
            "children": children,
        })
    grouped.sort(key=lambda item: item["name"])
    return grouped


def _occupants(crm, event_id: str) -> List[dict]:
    filt = f"_aha_event_value eq {event_id} and statecode eq 0"
    try:
        rows = crm._paginate(
            "aha_tablereservations?$select=_aha_table_value,_aha_contact_value"
            "&$expand=aha_Contact($select=fullname,emailaddress1)"
            f"&$filter={requests.utils.quote(filt)}"
        )
    except Exception:
        rows = crm._paginate(
            "aha_tablereservations?$select=_aha_table_value,_aha_contact_value"
            f"&$filter={requests.utils.quote(filt)}"
        )
    people = []
    for row in rows:
        contact = row.get("aha_Contact") or {}
        people.append({
            "id": row.get("_aha_contact_value") or "",
            "name": contact.get("fullname") or "Guest",
            "email": contact.get("emailaddress1") or "",
            "table_id": row.get("_aha_table_value") or "",
        })
    return people


def _layout_points(placed: List[dict], width: int, height: int) -> List[tuple]:
    aspect = (height / width) if width else 1
    return [(float(item["cx"]), float(item["cy"]) * aspect) for item in placed]


def _nearest_gaps(points: List[tuple]) -> List[float]:
    gaps = []
    for index, (x, y) in enumerate(points):
        nearest = None
        for other, (ox, oy) in enumerate(points):
            if index == other:
                continue
            distance = ((x - ox) ** 2 + (y - oy) ** 2) ** 0.5
            if nearest is None or distance < nearest:
                nearest = distance
        if nearest and nearest > 0.3:
            gaps.append(nearest)
    return gaps


def _neighbor_gap(gaps: List[float]) -> float:
    """Column spacing. Ignore the long gaps across a dance floor."""
    ordered = sorted(gap for gap in gaps if gap > 0)
    if not ordered:
        return 0
    close = ordered[:max(1, (len(ordered) + 1) // 2)]
    return close[len(close) // 2]


def drop_stacked(placed: List[dict], width: int, height: int) -> List[dict]:
    """One circle per spot. A second number on the same circle is not drawn there."""
    if len(placed) < 3:
        return placed
    points = _layout_points(placed, width, height)
    typical = _neighbor_gap(_nearest_gaps(points))
    if typical <= 0:
        return placed
    limit = typical * 0.55
    kept = []
    kept_points = []
    for item, point in zip(placed, points):
        if any((point[0] - other[0]) ** 2 + (point[1] - other[1]) ** 2 < limit ** 2 for other in kept_points):
            continue
        kept.append(item)
        kept_points.append(point)
    return kept


def same_table_radius(placed: List[dict], width: int, height: int) -> float:
    """One radius for every table, small enough that neighbors do not overlap."""
    if len(placed) < 2:
        return 2.5
    gaps = _nearest_gaps(_layout_points(placed, width, height))
    typical = _neighbor_gap(gaps)
    if typical <= 0:
        return 2.5
    real = [gap for gap in gaps if gap >= typical * 0.55]
    closest = min(real) if real else typical
    return round(closest * 0.45, 2)


def seating_board(desk, event_id: str, contact_id: str = "", sketch: bool = False) -> dict:
    """The saved floor plan plus who is seated.

    A sketch skips the reservation list so the circles can draw before the
    names come back.
    """
    tables = desk.live_tables(
        event_id,
        contact_id,
        include_people=not sketch,
        with_reservations=not sketch,
    )
    layout = ensure_layout(desk.crm, event_id, tables)
    placed = [dict(row) for row in (layout.get("tables") or [])]
    if placed and not placed[0].get("r"):
        shared = same_table_radius(placed, layout.get("width") or 0, layout.get("height") or 0)
        for row in placed:
            row["r"] = shared
    matched = {(row.get("id") or "").lower() for row in placed}
    return {
        "tables": tables,
        "layout": {
            "width": layout.get("width") or 0,
            "height": layout.get("height") or 0,
            "tables": placed,
            "landmarks": layout.get("landmarks") or [],
        },
        "unmatched": [table for table in tables if table["id"].lower() not in matched],
        "live": not sketch,
    }


def guests_for_event(desk, event_id: str, query: str) -> List[dict]:
    filt = f"_crca7_event_value eq {event_id} and statecode eq 0"
    rows = desk.crm._make_request(
        "crca7_eventguests?$select=_crca7_existingcontact_value,statuscode"
        "&$expand=crca7_ExistingContact($select=fullname,emailaddress1)"
        f"&$filter={requests.utils.quote(filt)}&$top=200"
    ).get("value") or []
    needle = (query or "").strip().lower()
    people = []
    for row in rows:
        contact = row.get("crca7_ExistingContact") or {}
        name = contact.get("fullname") or ""
        email = contact.get("emailaddress1") or ""
        if needle and needle not in name.lower() and needle not in email.lower():
            continue
        contact_id = row.get("_crca7_existingcontact_value") or ""
        if contact_id:
            people.append({"id": contact_id, "name": name or email or "Guest", "email": email})
    return people[:30]
