"""Keyword-based job filtering."""

from __future__ import annotations

import re

from models import Job


def _keyword_matches(text: str, keyword: str, use_word_boundary: bool = False) -> bool:
    """Check if keyword matches in text. Optionally use word boundary matching."""
    if use_word_boundary:
        pattern = r"\b" + re.escape(keyword) + r"\b"
        return bool(re.search(pattern, text, re.IGNORECASE))
    return keyword in text


def apply_filters(jobs: list[Job], filters: dict | None) -> list[Job]:
    """Filter jobs based on keyword groups and location.

    AND logic between all groups:
    - Title must match >=1 intern_keyword (word boundary match)
    - Title must match >=1 role_keyword (substring match)
    - Location must match >=1 location_keyword (substring match)
    """
    if not filters:
        return jobs

    intern_keywords = filters.get("intern_keywords", [])
    role_keywords = filters.get("role_keywords", [])
    location_keywords = filters.get("location_keywords", [])
    case_sensitive = filters.get("case_sensitive", False)

    if not intern_keywords and not role_keywords and not location_keywords:
        return jobs

    filtered = []
    for job in jobs:
        title = job["title"] if case_sensitive else job["title"].lower()
        location = job.get("location", "") or ""
        if not case_sensitive:
            location = location.lower()

        # Intern keywords: word boundary match to prevent "International" false positives
        intern_match = not intern_keywords
        for kw in intern_keywords:
            check_kw = kw if case_sensitive else kw.lower()
            if _keyword_matches(title, check_kw, use_word_boundary=True):
                intern_match = True
                break

        # Role keywords: substring match
        role_match = not role_keywords
        for kw in role_keywords:
            check_kw = kw if case_sensitive else kw.lower()
            if check_kw in title:
                role_match = True
                break

        # Location keywords: substring match
        location_match = not location_keywords
        for kw in location_keywords:
            check_kw = kw if case_sensitive else kw.lower()
            if check_kw in location:
                location_match = True
                break

        if intern_match and role_match and location_match:
            filtered.append(job)

    return filtered
