"""Diff logic — detect new jobs and filter by recency."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from models import Job


def find_new_jobs(previous: list[Job], current: list[Job]) -> list[Job]:
    """Find jobs in current that were not in previous (by ID)."""
    previous_ids = {job["id"] for job in previous}
    return [job for job in current if job["id"] not in previous_ids]


def filter_recent_jobs(jobs: list[Job], max_age_days: int = 3) -> list[Job]:
    """Keep only jobs posted within the last max_age_days days.

    If posted_date cannot be parsed or is missing, the job is kept
    (better to over-notify than to miss a position).
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_age_days)
    result = []

    for job in jobs:
        posted = job.get("posted_date", "")
        if not posted:
            result.append(job)
            continue

        parsed = _parse_posted_date(posted)
        if parsed is None:
            result.append(job)
            continue

        if parsed >= cutoff:
            result.append(job)

    return result


def _parse_posted_date(date_str: str) -> datetime | None:
    """Try to parse various posted_date formats into a datetime."""

    # ISO 8601: "2026-02-24T10:00:00+0000" or "2026-02-24"
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    # Amazon-style: "Month DD, YYYY" e.g. "November 15, 2025"
    try:
        dt = datetime.strptime(date_str.strip(), "%B %d, %Y")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # SerpApi relative: "X days ago", "X hours ago"
    match = re.match(
        r"(\d+)\s+(hour|day|week|month)s?\s+ago", date_str.strip(), re.IGNORECASE
    )
    if match:
        n = int(match.group(1))
        unit = match.group(2).lower()
        delta_map = {
            "hour": timedelta(hours=n),
            "day": timedelta(days=n),
            "week": timedelta(weeks=n),
            "month": timedelta(days=n * 30),
        }
        return datetime.now(timezone.utc) - delta_map.get(unit, timedelta())

    return None
