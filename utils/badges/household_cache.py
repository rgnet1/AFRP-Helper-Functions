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


def enrich_dataframe(
    df: pd.DataFrame,
    crm_client: Optional["DynamicsCRMClient"],
    cache_path: str,
    contact_id_column: str = "Contact ID",
) -> pd.DataFrame:
    """
    Add Household ID / Household / Head of Household columns using the file cache.
    Fetches only cache misses from CRM when crm_client is provided.
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
    else:
        logger.info("Household cache hit for all %d contacts", len(contact_ids))

    def _lookup(contact_id: Any, field: str) -> str:
        entry = cached_contacts.get(str(contact_id).strip(), {})
        val = entry.get(field, "")
        return "" if val is None else str(val)

    df["Household ID"] = df[contact_id_column].map(lambda cid: _lookup(cid, "household_id"))
    df["Household"] = df[contact_id_column].map(lambda cid: _lookup(cid, "household"))
    df["Head of Household"] = df[contact_id_column].map(lambda cid: _lookup(cid, "head_of_household"))
    return df
