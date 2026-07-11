"""Persistent file cache for contact household fields (badge grouping)."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import pandas as pd

from utils.stats.crm_fields import (
    CONTACT_HEAD_OF_HOUSEHOLD_FIELD,
    CONTACT_HOUSEHOLD_FIELD,
)

if TYPE_CHECKING:
    from utils.dynamics_crm import DynamicsCRMClient

logger = logging.getLogger(__name__)

CACHE_VERSION = 1
HOUSEHOLD_COLUMNS = ("Household ID", "Household", "Head of Household")
FORMATTED_SUFFIX = "@OData.Community.Display.V1.FormattedValue"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_cache(path: str) -> dict:
    """Load cache JSON from disk; return empty structure if missing."""
    if not path or not os.path.exists(path):
        return {"version": CACHE_VERSION, "contacts": {}}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {"version": CACHE_VERSION, "contacts": {}}
        data.setdefault("version", CACHE_VERSION)
        data.setdefault("contacts", {})
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read household cache %s: %s", path, exc)
        return {"version": CACHE_VERSION, "contacts": {}}


def save_cache(path: str, data: dict) -> None:
    """Write cache atomically (temp file + rename)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data["version"] = CACHE_VERSION
    fd, tmp_path = tempfile.mkstemp(
        dir=os.path.dirname(path) or ".",
        prefix=".household_cache_",
        suffix=".json",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_missing_contact_ids(contact_ids: List[str], cache: dict) -> List[str]:
    """Return contact IDs not present in cache.contacts."""
    cached = cache.get("contacts") or {}
    seen = set()
    missing = []
    for cid in contact_ids:
        key = str(cid).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        if key not in cached:
            missing.append(key)
    return missing


def parse_contact_household_fields(contact: dict) -> dict:
    """Extract household fields from a CRM contact record."""
    contact_id = contact.get("contactid")
    if not contact_id:
        return {}

    hh_guid = contact.get(CONTACT_HOUSEHOLD_FIELD)
    hh_label_key = f"{CONTACT_HOUSEHOLD_FIELD}{FORMATTED_SUFFIX}"
    household_label = contact.get(hh_label_key)
    if household_label is None and hh_guid is not None:
        household_label = str(hh_guid)

    head_key = CONTACT_HEAD_OF_HOUSEHOLD_FIELD
    head_fmt = f"{head_key}{FORMATTED_SUFFIX}"
    head = contact.get(head_fmt) if head_fmt in contact else contact.get(head_key)
    if head is True or str(head).lower() in ("true", "1"):
        head = "Yes"
    elif head is False or str(head).lower() in ("false", "0"):
        head = "No"
    elif head is not None:
        head = str(head).strip()

    return {
        "household_id": str(hh_guid).strip() if hh_guid else "",
        "household": str(household_label).strip() if household_label else "",
        "head_of_household": head or "",
        "cached_at": _utc_now_iso(),
    }


def merge_fetched_into_cache(cache: dict, fetched: Dict[str, dict]) -> None:
    contacts = cache.setdefault("contacts", {})
    for contact_id, entry in fetched.items():
        contacts[str(contact_id).strip()] = entry


def _nonempty(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return text


def seed_cache_from_dataframe(
    df: pd.DataFrame,
    cache: dict,
    contact_id_column: str = "Contact ID",
) -> int:
    """
    Populate cache entries from household columns already present on the dataframe
    (e.g. from the event-guest CRM export). Returns how many contacts were seeded.
    """
    if contact_id_column not in df.columns:
        return 0
    if not any(col in df.columns for col in HOUSEHOLD_COLUMNS):
        return 0

    seeded = 0
    contacts = cache.setdefault("contacts", {})
    now = _utc_now_iso()
    for _, row in df[[c for c in [contact_id_column, *HOUSEHOLD_COLUMNS] if c in df.columns]].iterrows():
        contact_id = _nonempty(row.get(contact_id_column))
        if not contact_id or contact_id in contacts:
            continue
        household_id = _nonempty(row.get("Household ID"))
        household = _nonempty(row.get("Household"))
        head = _nonempty(row.get("Head of Household"))
        if not (household_id or household or head):
            continue
        contacts[contact_id] = {
            "household_id": household_id,
            "household": household,
            "head_of_household": head,
            "cached_at": now,
        }
        seeded += 1
    return seeded


def enrich_dataframe(
    df: pd.DataFrame,
    crm_client: Optional["DynamicsCRMClient"],
    cache_path: str,
    contact_id_column: str = "Contact ID",
) -> pd.DataFrame:
    """
    Add Household ID / Household / Head of Household columns using the file cache.
    Prefers values already on the dataframe (event-guest export), then cache hits,
    and only then fetches remaining misses from CRM.
    """
    if df.empty or contact_id_column not in df.columns:
        return df

    for col in HOUSEHOLD_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    contact_ids = [
        str(v).strip()
        for v in df[contact_id_column].dropna().unique()
        if str(v).strip()
    ]
    if not contact_ids:
        return df

    cache = load_cache(cache_path)
    seeded = seed_cache_from_dataframe(df, cache, contact_id_column)
    if seeded:
        save_cache(cache_path, cache)
        logger.info(
            "Seeded household cache with %d contact(s) from registration data",
            seeded,
        )

    cached_contacts = cache.get("contacts") or {}
    missing = get_missing_contact_ids(contact_ids, cache)

    if missing:
        if crm_client is None:
            logger.warning(
                "Household cache miss for %d contact(s) but no CRM client available",
                len(missing),
            )
        else:
            logger.info(
                "Household cache miss: fetching %d of %d contacts from CRM",
                len(missing),
                len(contact_ids),
            )
            fetched = crm_client.fetch_contact_households(missing)
            merge_fetched_into_cache(cache, fetched)
            save_cache(cache_path, cache)
            cached_contacts = cache.get("contacts") or {}
            logger.info(
                "Household CRM fetch complete: cached %d of %d requested contact(s)",
                len(fetched),
                len(missing),
            )
    else:
        logger.info("Household cache hit for all %d contacts", len(contact_ids))

    def _lookup(contact_id: Any, field: str) -> str:
        entry = cached_contacts.get(str(contact_id).strip(), {})
        val = entry.get(field, "")
        return "" if val is None else str(val)

    # Prefer non-empty values already on the dataframe; fill gaps from cache.
    for col, cache_field in (
        ("Household ID", "household_id"),
        ("Household", "household"),
        ("Head of Household", "head_of_household"),
    ):
        existing = df[col].map(_nonempty)
        from_cache = df[contact_id_column].map(lambda cid: _lookup(cid, cache_field))
        df[col] = existing.where(existing.ne(""), from_cache)
    return df
