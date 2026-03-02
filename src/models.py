"""Shared data models for new-position-monitor."""

from __future__ import annotations

from typing import List, Optional, TypedDict


class Job(TypedDict, total=False):
    """Normalized job listing from any ATS."""

    id: str
    title: str
    location: str
    department: Optional[str]
    url: str
    posted_date: str
    updated_at: str
