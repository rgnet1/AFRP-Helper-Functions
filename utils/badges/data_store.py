"""Memory-aware badge pipeline data spool (Parquet) and job serialization."""

from __future__ import annotations

import gc
import logging
import os
import threading
from contextlib import contextmanager
from typing import Dict, Iterator, Optional

import pandas as pd

from utils.badges.file_validator import FileTypes, FileValidator

logger = logging.getLogger(__name__)

_BADGE_PIPELINE_LOCK = threading.Lock()

MEMORY_MIN_AVAILABLE_MB = int(os.environ.get("BADGE_MEMORY_MIN_AVAILABLE_MB", "256"))
PARALLEL_LOAD_MAX_MB = int(os.environ.get("BADGE_PARALLEL_LOAD_MAX_MB", "80"))
IN_MEMORY_ROW_THRESHOLD = int(os.environ.get("BADGE_IN_MEMORY_ROW_THRESHOLD", "3000"))

CRM_DATA_SUFFIX = "_crm_data"


class PipelineBusyError(RuntimeError):
    """Raised when a second heavy badge pipeline job is attempted."""


class InsufficientMemoryError(RuntimeError):
    """Raised when available system memory is below the configured threshold."""


def _memory_available_mb() -> Optional[float]:
    """Return available memory in MB, or None if unknown."""
    try:
        import psutil

        return psutil.virtual_memory().available / (1024 * 1024)
    except Exception:
        pass
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb / 1024
    except OSError:
        pass
    return None


def check_memory_available(min_mb: Optional[int] = None) -> None:
    """Raise InsufficientMemoryError if free memory is below min_mb."""
    threshold = MEMORY_MIN_AVAILABLE_MB if min_mb is None else min_mb
    available = _memory_available_mb()
    if available is None:
        return
    if available < threshold:
        raise InsufficientMemoryError(
            f"Insufficient memory to start badge processing "
            f"({available:.0f} MB available, {threshold} MB required). "
            "Try again later or reduce concurrent load."
        )


@contextmanager
def badge_pipeline_job() -> Iterator[None]:
    """Allow only one heavy pull/merge/generate pipeline job at a time."""
    acquired = _BADGE_PIPELINE_LOCK.acquire(blocking=False)
    if not acquired:
        raise PipelineBusyError(
            "Another badge data job is already running. Please wait for it to finish."
        )
    try:
        check_memory_available()
        yield
    finally:
        _BADGE_PIPELINE_LOCK.release()


def _parquet_path(directory: str, file_type: str) -> str:
    return os.path.join(directory, f"{file_type}{CRM_DATA_SUFFIX}.parquet")


def _excel_path(directory: str, file_type: str) -> str:
    return os.path.join(directory, f"{file_type}{CRM_DATA_SUFFIX}.xlsx")


def _estimate_paths_mb(paths: Dict[str, str]) -> float:
    total = 0
    for path in paths.values():
        if path and os.path.exists(path):
            total += os.path.getsize(path)
    return total / (1024 * 1024)


class BadgeDataStore:
    """Spill badge source DataFrames to Parquet; load one stage at a time when needed."""

    def __init__(self, directory: str):
        self.directory = directory
        os.makedirs(directory, mode=0o777, exist_ok=True)

    def spool(self, file_type: str, df: pd.DataFrame) -> str:
        """Write a slim DataFrame to Parquet and return the path."""
        path = _parquet_path(self.directory, file_type)
        df.to_parquet(path, index=False)
        logger.info(
            "Spooled %s (%d rows, %d cols) to Parquet",
            file_type,
            len(df),
            len(df.columns),
        )
        return path

    def spool_excel_legacy(self, file_type: str, df: pd.DataFrame) -> str:
        """Optional Excel copy for manual download / legacy tooling."""
        path = _excel_path(self.directory, file_type)
        df.to_excel(path, index=False)
        return path

    def remove_existing(self, file_type: str) -> None:
        for path in (_parquet_path(self.directory, file_type), _excel_path(self.directory, file_type)):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError as exc:
                logger.warning("Could not remove %s: %s", path, exc)

    @staticmethod
    def find_source_paths(directory: str = ".") -> Dict[str, str]:
        """Return full paths for each file type (Parquet preferred over Excel)."""
        paths: Dict[str, str] = {}
        missing = []
        for file_type in FileValidator.get_required_file_types():
            parquet = _parquet_path(directory, file_type)
            excel = _excel_path(directory, file_type)
            if os.path.exists(parquet):
                paths[file_type] = parquet
            elif os.path.exists(excel):
                paths[file_type] = excel
            else:
                missing.append(file_type)
        if not missing:
            return paths
        if len(missing) == len(FileValidator.get_required_file_types()):
            legacy = FileValidator.find_latest_files(directory)
            return {
                file_type: os.path.join(directory, legacy[file_type])
                for file_type in legacy
            }
        raise ValueError(f"Missing required badge source files: {', '.join(missing)}")

    @staticmethod
    def load_frame(path: str) -> pd.DataFrame:
        if path.lower().endswith(".parquet"):
            return pd.read_parquet(path)
        return pd.read_excel(path)

    @staticmethod
    def load_all_sequential(paths: Dict[str, str]) -> Dict[str, pd.DataFrame]:
        """Load each source file one at a time to limit peak RAM."""
        frames: Dict[str, pd.DataFrame] = {}
        for file_type in FileValidator.get_required_file_types():
            path = paths[file_type]
            logger.debug("Loading %s from %s", file_type, path)
            frames[file_type] = BadgeDataStore.load_frame(path)
        return frames

    @staticmethod
    def load_all(paths: Dict[str, str]) -> Dict[str, pd.DataFrame]:
        """Load sources sequentially or in parallel based on estimated file size."""
        estimated_mb = _estimate_paths_mb(paths)
        if estimated_mb <= PARALLEL_LOAD_MAX_MB:
            from concurrent.futures import ThreadPoolExecutor

            logger.info(
                "Parallel-loading badge sources (~%.1f MB on disk)", estimated_mb
            )
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {
                    ft: pool.submit(BadgeDataStore.load_frame, paths[ft])
                    for ft in FileValidator.get_required_file_types()
                }
                return {ft: fut.result() for ft, fut in futures.items()}
        logger.info(
            "Sequential-loading badge sources (~%.1f MB on disk)", estimated_mb
        )
        return BadgeDataStore.load_all_sequential(paths)

    @staticmethod
    def release_frames(frames: Dict[str, pd.DataFrame]) -> None:
        frames.clear()
        gc.collect()


CRM_PULL_SEQUENCE = (
    ("event_guests", FileTypes.REGISTRATION),
    ("qr_codes", FileTypes.QR_CODES),
    ("table_reservations", FileTypes.SEATING),
    ("form_responses", FileTypes.FORM_RESPONSES),
)


def pull_campaign_to_store(
    crm_client,
    campaign_id: str,
    store: BadgeDataStore,
    *,
    write_excel: bool = False,
) -> None:
    """Pull CRM data sequentially, spool slim Parquet, and release each frame."""
    import numpy as np

    for data_type, file_type in CRM_PULL_SEQUENCE:
        store.remove_existing(file_type)
        df = crm_client.download_data_by_type_filtered(data_type, None, campaign_id)
        if data_type == "table_reservations" and "Event" in df.columns:
            df["Event"] = df["Event"].replace({np.nan: "", None: ""})
            df["Event"] = df["Event"].astype(str).replace("nan", "").replace("None", "")
        store.spool(file_type, df)
        if write_excel:
            store.spool_excel_legacy(file_type, df)
        del df
        gc.collect()
