"""Tests for badge merge performance and memory-aware data store."""

import tempfile
import threading
import time

import pandas as pd
import pytest

from utils.badges.convert_to_mail_merge_v3 import EventRegistrationProcessorV3
from utils.badges.data_store import (
    BadgeDataStore,
    PipelineBusyError,
    badge_pipeline_job,
)
from utils.badges.file_validator import FileTypes


def _sample_registration_paid():
    return pd.DataFrame(
        {
            "Contact ID": ["c1", "c1", "c2", "c3"],
            "Member ID (Existing Contact) (Contact)": ["ID-1", "ID-1", "ID-2", "ID-3"],
            "First Name (Existing Contact) (Contact)": ["alice", "alice", "bob", "carol"],
            "Middle Name (Existing Contact) (Contact)": ["", "", "", ""],
            "Last Name (Existing Contact) (Contact)": ["alpha", "alpha", "beta", "gamma"],
            "Maiden Name (Existing Contact) (Contact)": ["", "", "", ""],
            "Title (Existing Contact) (Contact)": ["", "", "", ""],
            "Local Club (Existing Contact) (Contact)": ["Club A", "Club A", "Club B", "Club C"],
            "Gender (Existing Contact) (Contact)": ["2", "2", "1", "2"],
            "Age (Existing Contact) (Contact)": [30, 30, 40, 50],
            "Household ID (Existing Contact) (Contact)": ["", "", "", ""],
            "Household (Existing Contact) (Contact)": ["", "", "", ""],
            "Head of Household (Existing Contact) (Contact)": ["", "", "", ""],
            "Event": ["Gala", "Workshop", "Gala", "Gala"],
            "Status Reason": ["Paid", "Paid", "Paid", "Paid"],
            "Created On": [
                "2026-01-01 10:00:00",
                "2026-01-02 10:00:00",
                "2026-01-03 10:00:00",
                "2026-01-04 10:00:00",
            ],
        }
    )


def test_vectorized_event_registration_columns():
    processor = EventRegistrationProcessorV3()
    reg_df = _sample_registration_paid()
    result = processor.process_registration_data(reg_df)

    assert len(result) == 3
    assert "Gala" in result.columns
    assert "Workshop" in result.columns
    assert result.loc[result["Contact ID"] == "c1", "Gala"].iloc[0] == "Gala"
    assert result.loc[result["Contact ID"] == "c1", "Workshop"].iloc[0] == "Workshop"
    assert result.loc[result["Contact ID"] == "c2", "Gala"].iloc[0] == "Gala"
    assert pd.isna(result.loc[result["Contact ID"] == "c2", "Workshop"].iloc[0])


def test_seating_merge_vectorized():
    processor = EventRegistrationProcessorV3()
    base = processor.process_registration_data(_sample_registration_paid())
    seating = pd.DataFrame(
        {
            "Contact ID": ["c1", "c2"],
            "Event": ["Gala", "Gala"],
            "Table": ["12", "15"],
            "Created On": ["2026-01-01", "2026-01-02"],
        }
    )
    result = processor.add_seating_info(base, seating)
    assert result.loc[result["Contact ID"] == "c1", "Gala ~ Table"].iloc[0] == "12"
    assert result.loc[result["Contact ID"] == "c2", "Gala ~ Table"].iloc[0] == "15"


def test_date_filter_uses_cached_registration_created_on():
    from utils.badges.pre_processing_module import PreprocessingConfig

    config = PreprocessingConfig(
        main_event="Default",
        created_on_filter="1/2/2026",
    )
    processor = EventRegistrationProcessorV3(config=config)
    processor.process_registration_data(_sample_registration_paid())
    ids = processor._date_filter_contact_ids()
    assert ids == {"c2", "c3"}


def test_badge_data_store_spool_and_load():
    reg = _sample_registration_paid()
    with tempfile.TemporaryDirectory() as tmp:
        store = BadgeDataStore(tmp)
        path = store.spool(FileTypes.REGISTRATION, reg)
        assert path.endswith(".parquet")
        loaded = BadgeDataStore.load_frame(path)
        assert len(loaded) == len(reg)


def test_badge_pipeline_job_single_flight():
    results = []

    def worker():
        try:
            with badge_pipeline_job():
                time.sleep(0.2)
                results.append("ok")
        except PipelineBusyError:
            results.append("busy")

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    time.sleep(0.05)
    t2.start()
    t1.join()
    t2.join()

    assert sorted(results) == ["busy", "ok"]
