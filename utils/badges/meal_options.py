"""Detect meal-preference form questions and aggregate CRM choice labels."""

from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd

from utils.dynamics_crm import parse_choice_labels

logger = logging.getLogger(__name__)

# Merged badge column that coalesces per-banquet meal-preference form responses.
MEAL_PREFERENCE_COLUMN = "Meal Preference"

MEAL_QUESTION_INCLUDE = re.compile(
    r"vegetarian|vegan|\bentr[ée]e\b|meal\s*(preference|choice|option|selection)"
    r"|dinner\s*(preference|choice|option|selection)|dietary",
    re.IGNORECASE,
)
MEAL_QUESTION_EXCLUDE = re.compile(
    r"child|kid|allerg|potty|t[\s-]*shirt|babysit",
    re.IGNORECASE,
)


def is_meal_question(question: str) -> bool:
    """True when question text looks like a meal/dietary choice (not logistics)."""
    if not question:
        return False
    return bool(MEAL_QUESTION_INCLUDE.search(question)) and not bool(
        MEAL_QUESTION_EXCLUDE.search(question)
    )


def is_banquet_event(campaign_name: str) -> bool:
    """Heuristic: banquet halls / ballroom sub-events."""
    name = (campaign_name or "").lower()
    return "banquet" in name or "ballroom" in name


def meal_response_column(campaign_name: str, question: str) -> str:
    """Excel column name for a form-response meal question."""
    return f"{campaign_name} ~ {question}"


def is_registered_for_event(row: dict, event_name: str) -> bool:
    """True when the attendee has a paid registration column for this event."""
    if not event_name:
        return False
    value = row.get(event_name)
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(str(value).strip())


def _cell_str(row: dict, column: str) -> str:
    if column not in row:
        return ""
    value = row[column]
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text


def apply_meal_preference_mapping(raw_value: Any, mappings: dict | None) -> str:
    """Column-scoped lookup for a single meal response value."""
    if raw_value is None:
        return ""
    text = str(raw_value).strip()
    if not text:
        return ""
    if not mappings:
        return text
    if text in mappings:
        mapped = mappings[text]
        return "" if mapped is None else str(mapped).strip()
    return text


def default_source_config(questions: list[dict[str, Any]]) -> dict[str, dict]:
    """
    Default badge-source toggles: banquets on, other meal events off.

    Keys are Excel column names ``{campaign} ~ {question}``.
    """
    config: dict[str, dict] = {}
    for index, item in enumerate(questions):
        campaign = (item.get("campaign_name") or "").strip()
        question = (item.get("question") or "").strip()
        column = item.get("column") or meal_response_column(campaign, question)
        is_banquet = bool(item.get("is_banquet", is_banquet_event(campaign)))
        config[column] = {
            "enabled": is_banquet,
            "is_banquet": is_banquet,
            "order": index,
            "campaign_name": campaign,
            "question": question,
        }
    return config


def build_meal_preference_value(
    row: dict,
    sources_config: dict[str, dict] | None,
    mappings: dict | None = None,
) -> str:
    """
    Build the badge meal label from enabled per-event form responses.

    - Banquet halls: only the banquet the attendee registered for (one room).
    - Other meal events: included only when enabled in sources_config.
    - Multiple enabled values are mapped individually and joined with a space.
    """
    if not sources_config:
        return ""

    ordered: list[tuple[int, str, dict]] = []
    for column, cfg in sources_config.items():
        if not cfg.get("enabled"):
            continue
        order = int(cfg.get("order", 0))
        ordered.append((order, column, cfg))
    ordered.sort(key=lambda item: (0 if not item[2].get("is_banquet") else 1, item[0], item[1]))

    non_banquet_parts: list[str] = []
    banquet_part = ""

    for _, column, cfg in ordered:
        if " ~ " not in column:
            continue
        event_name = column.split(" ~ ", 1)[0]
        if not is_registered_for_event(row, event_name):
            continue

        raw = _cell_str(row, column)
        if not raw:
            continue
        mapped = apply_meal_preference_mapping(raw, mappings)
        if not mapped:
            continue

        if cfg.get("is_banquet"):
            if not banquet_part:
                banquet_part = mapped
        else:
            non_banquet_parts.append(mapped)

    return " ".join(non_banquet_parts + ([banquet_part] if banquet_part else []))


def aggregate_meal_options(questions: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Filter meal questions and return union of distinct choice labels.

    Each question dict is expected to have: campaign_name, question, question_type,
    choice_labels (list of strings).
    """
    meal_questions = []
    options: list[str] = []
    seen: set[str] = set()

    for index, item in enumerate(questions):
        question = (item.get("question") or "").strip()
        if not is_meal_question(question):
            continue
        campaign = (item.get("campaign_name") or "").strip()
        labels = item.get("choice_labels") or []
        column = meal_response_column(campaign, question)
        is_banquet = is_banquet_event(campaign)
        meal_questions.append(
            {
                "campaign_id": item.get("campaign_id"),
                "campaign_name": campaign,
                "question": question,
                "question_type": item.get("question_type") or "",
                "column": column,
                "is_banquet": is_banquet,
                "default_enabled": is_banquet,
                "order": index,
                "options": labels,
            }
        )
        for label in labels:
            key = str(label).strip()
            if key and key not in seen:
                seen.add(key)
                options.append(key)

    return {
        "questions": meal_questions,
        "options": options,
        "has_meal_questions": bool(meal_questions),
        "default_sources": default_source_config(meal_questions),
    }
