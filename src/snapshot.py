"""Snapshot storage — save/load job listings to disk."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR
from models import Job


def snapshot_path(company: dict) -> Path:
    """Get the snapshot file path for a company."""
    return DATA_DIR / f"{company['ats']}_{company['slug']}.json"


def load_snapshot(company: dict) -> list[Job]:
    """Load previous job snapshot. Returns empty list on first run."""
    path = snapshot_path(company)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("jobs", [])


def save_snapshot(company: dict, jobs: list[Job]) -> None:
    """Save current job snapshot to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    data = {
        "company": company["name"],
        "ats": company["ats"],
        "slug": company["slug"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "jobs": jobs,
    }

    path = snapshot_path(company)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
