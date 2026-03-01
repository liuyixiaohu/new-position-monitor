#!/usr/bin/env python3
"""
NewPositionMonitor - Monitor target companies for new job positions via ATS APIs.

Fetches job listings from Greenhouse, Lever, and Ashby public APIs,
compares against previous snapshots, and creates a GitHub Issue
when new positions are found.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

# --- Constants ---
DATA_DIR = Path(__file__).parent / "data"
CONFIG_FILE = Path(__file__).parent / "companies.yaml"
REQUEST_TIMEOUT = 30  # seconds


# =============================================================================
# Config Loading
# =============================================================================

def load_config(path: str = None) -> dict:
    """Load and validate companies.yaml config."""
    config_path = Path(path) if path else CONFIG_FILE
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not config or "companies" not in config:
        print("ERROR: Config file must contain a 'companies' list.")
        sys.exit(1)

    for company in config["companies"]:
        required = ["name", "ats", "slug"]
        for field in required:
            if field not in company:
                print(f"ERROR: Company entry missing '{field}': {company}")
                sys.exit(1)
        if company["ats"] not in ("greenhouse", "lever", "ashby", "amazon", "workday", "smartrecruiters", "phenom", "icims", "serpapi"):
            print(f"ERROR: Unknown ATS type '{company['ats']}' for {company['name']}")
            sys.exit(1)

    return config


# =============================================================================
# ATS Fetchers — each returns a list of normalized job dicts
# =============================================================================

def fetch_jobs(company: dict) -> list[dict]:
    """Dispatch to the correct ATS fetcher."""
    ats = company["ats"]
    slug = company["slug"]

    if ats == "workday":
        return fetch_workday(company)
    if ats == "amazon":
        return fetch_amazon()
    if ats == "smartrecruiters":
        return fetch_smartrecruiters(slug)
    if ats == "phenom":
        return fetch_phenom(company)
    if ats == "icims":
        return fetch_icims(company)
    if ats == "serpapi":
        return fetch_serpapi(company)

    fetchers = {
        "greenhouse": fetch_greenhouse,
        "lever": fetch_lever,
        "ashby": fetch_ashby,
    }
    return fetchers[ats](slug)


def fetch_greenhouse(slug: str) -> list[dict]:
    """Fetch jobs from Greenhouse public API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    jobs = []
    for job in data.get("jobs", []):
        jobs.append({
            "id": str(job.get("id", "")),
            "title": job.get("title", ""),
            "location": job.get("location", {}).get("name", ""),
            "department": None,  # Greenhouse doesn't provide department
            "url": job.get("absolute_url", ""),
            "posted_date": job.get("first_published", ""),
            "updated_at": job.get("updated_at", ""),
        })
    return jobs


def fetch_lever(slug: str) -> list[dict]:
    """Fetch jobs from Lever public API."""
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    jobs = []
    for job in data if isinstance(data, list) else []:
        # Lever createdAt is Unix timestamp in milliseconds
        created_at = job.get("createdAt")
        posted_date = ""
        if created_at:
            try:
                posted_date = datetime.fromtimestamp(
                    created_at / 1000, tz=timezone.utc
                ).isoformat()
            except (ValueError, TypeError, OSError):
                pass

        categories = job.get("categories", {})
        jobs.append({
            "id": str(job.get("id", "")),
            "title": job.get("text", ""),
            "location": categories.get("location", ""),
            "department": categories.get("department", ""),
            "url": job.get("hostedUrl", ""),
            "posted_date": posted_date,
            "updated_at": "",
        })
    return jobs


def fetch_ashby(slug: str) -> list[dict]:
    """Fetch jobs from Ashby public API."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    params = {"includeCompensation": "true"}
    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    jobs = []
    for job in data.get("jobs", []):
        jobs.append({
            "id": str(job.get("id", "")),
            "title": job.get("title", ""),
            "location": job.get("location", ""),
            "department": job.get("department", ""),
            "url": job.get("jobUrl", ""),
            "posted_date": job.get("publishedAt", ""),
            "updated_at": "",
        })
    return jobs


def fetch_amazon() -> list[dict]:
    """Fetch jobs from Amazon's public search API. Paginates through all results."""
    base_url = "https://www.amazon.jobs/en/search.json"
    all_jobs = []
    offset = 0
    page_size = 100

    while True:
        params = {
            "offset": offset,
            "result_limit": page_size,
            "sort": "recent",
            "country": "USA",
        }
        resp = requests.get(base_url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        hits = data.get("jobs", [])
        if not hits:
            break

        for job in hits:
            job_id = job.get("id_icims") or job.get("id") or ""
            posted = job.get("posted_date", "")

            all_jobs.append({
                "id": str(job_id),
                "title": job.get("title", ""),
                "location": job.get("normalized_location", job.get("location", "")),
                "department": job.get("job_category", ""),
                "url": f"https://www.amazon.jobs{job.get('job_path', '')}",
                "posted_date": posted,
                "updated_at": job.get("updated_time", ""),
            })

        # Stop if we got fewer results than page size (last page)
        if len(hits) < page_size:
            break
        offset += page_size

        # Safety limit: don't fetch more than 10000 jobs
        if offset >= 10000:
            break

    return all_jobs


def fetch_workday(company: dict) -> list[dict]:
    """
    Fetch jobs from Workday's undocumented public API.

    NOTE: This is NOT an official API. It could break at any time.
    The endpoint is reverse-engineered from Workday career portals.
    """
    slug = company["slug"]
    site = company.get("workday_site", "External")
    instance = company.get("workday_instance", "wd1")

    base_url = (
        f"https://{slug}.{instance}.myworkdayjobs.com"
        f"/wday/cxs/{slug}/{site}/jobs"
    )

    all_jobs = []
    offset = 0
    page_size = 20  # Workday default

    while True:
        payload = {
            "limit": page_size,
            "offset": offset,
            "searchText": "",
        }
        headers = {"Content-Type": "application/json"}

        resp = requests.post(
            base_url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()

        postings = data.get("jobPostings", [])
        if not postings:
            break

        for job in postings:
            title = job.get("title", "")
            external_path = job.get("externalPath", "")
            job_url = (
                f"https://{slug}.{instance}.myworkdayjobs.com{external_path}"
                if external_path else ""
            )
            posted = job.get("postedOn", "")
            location_list = job.get("locationsText", "")

            # Workday uses bulletFields for location sometimes
            bullet_fields = job.get("bulletFields", [])
            if not location_list and bullet_fields:
                location_list = " | ".join(bullet_fields)

            all_jobs.append({
                "id": str(external_path or job.get("bulletFields", [""])[0]),
                "title": title,
                "location": location_list,
                "department": "",
                "url": job_url,
                "posted_date": posted,
                "updated_at": "",
            })

        # Check if there are more pages
        total = data.get("total", 0)
        offset += page_size
        if offset >= total:
            break

        # Safety limit
        if offset >= 10000:
            break

    return all_jobs


def fetch_smartrecruiters(slug: str) -> list[dict]:
    """Fetch jobs from SmartRecruiters public API."""
    base_url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    all_jobs = []
    offset = 0
    page_size = 100

    while True:
        params = {"offset": offset, "limit": page_size}
        resp = requests.get(base_url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        postings = data.get("content", [])
        if not postings:
            break

        for job in postings:
            location = job.get("location", {})
            location_str = location.get("fullLocation", "")
            if not location_str:
                parts = [location.get("city", ""), location.get("region", ""),
                         location.get("country", "")]
                location_str = ", ".join(p for p in parts if p)

            dept = job.get("department", {})
            dept_name = dept.get("label", "") if isinstance(dept, dict) else ""

            all_jobs.append({
                "id": str(job.get("id", "")),
                "title": job.get("name", ""),
                "location": location_str,
                "department": dept_name,
                "url": job.get("ref", ""),
                "posted_date": job.get("releasedDate", ""),
                "updated_at": "",
            })

        total = data.get("totalFound", 0)
        offset += page_size
        if offset >= total:
            break
        if offset >= 10000:
            break

    return all_jobs


def fetch_phenom(company: dict) -> list[dict]:
    """
    Fetch jobs from Phenom-powered career sites by parsing embedded JSON.

    Phenom renders job data server-side in a phApp.ddo JavaScript variable.
    This is HTML parsing — more fragile than API calls.
    """
    phenom_url = company.get("phenom_url", "")
    if not phenom_url:
        print(f"  ⚠️  No phenom_url configured for {company['name']}")
        return []

    all_jobs = []
    offset = 0
    page_size = 100

    while True:
        url = f"{phenom_url}?from={offset}&s=1"
        resp = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html",
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        content = resp.text

        # Find phApp.ddo JSON by matching braces
        match = re.search(r'phApp\.ddo\s*=\s*', content)
        if not match:
            print("  ⚠️  Could not find phApp.ddo in page")
            break

        start = match.end()
        depth = 0
        end = start
        for i in range(start, min(start + 500000, len(content))):
            if content[i] == '{':
                depth += 1
            elif content[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        try:
            data = json.loads(content[start:end])
        except json.JSONDecodeError:
            print("  ⚠️  Failed to parse phApp.ddo JSON")
            break

        search_data = data.get("eagerLoadRefineSearch", {}).get("data", {})
        jobs = search_data.get("jobs", [])

        if not jobs:
            break

        for job in jobs:
            location_parts = [
                job.get("city", ""),
                job.get("state", ""),
                job.get("country", ""),
            ]
            location_str = job.get("cityStateCountry", "")
            if not location_str:
                location_str = ", ".join(p for p in location_parts if p)

            apply_url = job.get("applyUrl", "")

            all_jobs.append({
                "id": str(job.get("jobId", "")),
                "title": job.get("title", ""),
                "location": location_str,
                "department": job.get("category", ""),
                "url": apply_url,
                "posted_date": job.get("postedDate", ""),
                "updated_at": job.get("dateCreated", ""),
            })

        # Phenom pages typically return 10 jobs; stop when we get fewer
        offset += len(jobs)
        if len(jobs) < 10:
            break
        if offset >= 10000:
            break

    return all_jobs


def fetch_icims(company: dict) -> list[dict]:
    """
    Fetch jobs from iCIMS-powered career sites (e.g., Rivian).

    Uses the public JSON API at {icims_url}?offset=N&limit=100.
    """
    icims_url = company.get("icims_url", "")
    if not icims_url:
        print(f"  ⚠️  No icims_url configured for {company['name']}")
        return []

    all_jobs = []
    offset = 0
    page_size = 100

    while True:
        params = {"offset": offset, "limit": page_size}
        resp = requests.get(icims_url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        postings = data.get("jobs", [])
        if not postings:
            break

        for job in postings:
            job_data = job.get("data", {})

            # Extract department from categories list
            categories = job_data.get("categories", [])
            dept = categories[0].get("name", "") if categories else ""

            all_jobs.append({
                "id": str(job_data.get("slug", "")),
                "title": job_data.get("title", ""),
                "location": job_data.get("location_name", ""),
                "department": dept,
                "url": job_data.get("apply_url", ""),
                "posted_date": job_data.get("posted_date", ""),
                "updated_at": job_data.get("update_date", ""),
            })

        total = data.get("totalCount", 0)
        offset += page_size
        if offset >= total:
            break
        if offset >= 10000:
            break

    return all_jobs


def fetch_serpapi(company: dict) -> list[dict]:
    """
    Fetch jobs via SerpApi's Google Jobs API.

    Used for companies with no direct ATS API (e.g., Tesla).
    Requires SERPAPI_KEY environment variable.
    """
    api_key = os.environ.get("SERPAPI_KEY", "")
    if not api_key:
        print(f"  ⚠️  SERPAPI_KEY not set, skipping {company['name']}")
        return []

    query = company.get("serpapi_query", "")
    if not query:
        print(f"  ⚠️  No serpapi_query configured for {company['name']}")
        return []

    all_jobs = []
    start = 0

    while True:
        params = {
            "engine": "google_jobs",
            "q": query,
            "api_key": api_key,
            "start": start,
        }
        # Add optional location bias
        gl = company.get("serpapi_gl", "us")
        if gl:
            params["gl"] = gl

        resp = requests.get(
            "https://serpapi.com/search", params=params, timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()

        jobs = data.get("jobs_results", [])
        if not jobs:
            break

        for job in jobs:
            # Build location string
            location = job.get("location", "")

            # Use job_id from SerpApi or fall back to title hash
            job_id = job.get("job_id", "")

            # Extract apply link (first option or empty)
            apply_options = job.get("apply_options", [])
            apply_url = apply_options[0].get("link", "") if apply_options else ""

            all_jobs.append({
                "id": str(job_id),
                "title": job.get("title", ""),
                "location": location,
                "department": job.get("company_name", ""),
                "url": apply_url,
                "posted_date": job.get("detected_extensions", {}).get("posted_at", ""),
                "updated_at": "",
            })

        # Google Jobs paginates in chunks of 10
        start += 10

        # SerpApi free tier: be conservative, max 2 pages per company
        if start >= 20:
            break

    return all_jobs


# =============================================================================
# Filtering
# =============================================================================

def _keyword_matches(text: str, keyword: str, use_word_boundary: bool = False) -> bool:
    """Check if keyword matches in text. Optionally use word boundary matching."""
    if use_word_boundary:
        # Use regex word boundary to prevent "intern" matching "International"
        pattern = r'\b' + re.escape(keyword) + r'\b'
        return bool(re.search(pattern, text, re.IGNORECASE))
    return keyword in text


def apply_filters(jobs: list[dict], filters: dict | None) -> list[dict]:
    """
    Filter jobs based on keyword groups and location.

    AND logic between all groups:
    - Title must match ≥1 intern_keyword (word boundary match)
    - Title must match ≥1 role_keyword (substring match)
    - Location must match ≥1 location_keywords (substring match)
    """
    if not filters:
        return jobs

    intern_keywords = filters.get("intern_keywords", [])
    role_keywords = filters.get("role_keywords", [])
    location_keywords = filters.get("location_keywords", [])
    case_sensitive = filters.get("case_sensitive", False)

    # If no keywords configured at all, return all
    if not intern_keywords and not role_keywords and not location_keywords:
        return jobs

    filtered = []
    for job in jobs:
        title = job["title"] if case_sensitive else job["title"].lower()
        location = job.get("location", "") or ""
        if not case_sensitive:
            location = location.lower()

        # Check intern keywords with WORD BOUNDARY (prevents "International" matching)
        intern_match = not intern_keywords
        for kw in intern_keywords:
            check_kw = kw if case_sensitive else kw.lower()
            if _keyword_matches(title, check_kw, use_word_boundary=True):
                intern_match = True
                break

        # Check role keywords (substring match is fine here)
        role_match = not role_keywords
        for kw in role_keywords:
            check_kw = kw if case_sensitive else kw.lower()
            if check_kw in title:
                role_match = True
                break

        # Check location keywords (substring match)
        location_match = not location_keywords
        for kw in location_keywords:
            check_kw = kw if case_sensitive else kw.lower()
            if check_kw in location:
                location_match = True
                break

        if intern_match and role_match and location_match:
            filtered.append(job)

    return filtered


# =============================================================================
# Snapshot Storage
# =============================================================================

def snapshot_path(company: dict) -> Path:
    """Get the snapshot file path for a company."""
    return DATA_DIR / f"{company['ats']}_{company['slug']}.json"


def load_snapshot(company: dict) -> list[dict]:
    """Load previous job snapshot. Returns empty list on first run."""
    path = snapshot_path(company)
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("jobs", [])


def save_snapshot(company: dict, jobs: list[dict]) -> None:
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


# =============================================================================
# Diff Logic
# =============================================================================

def find_new_jobs(previous: list[dict], current: list[dict]) -> list[dict]:
    """Find jobs in current that were not in previous (by ID)."""
    previous_ids = {job["id"] for job in previous}
    return [job for job in current if job["id"] not in previous_ids]


def filter_recent_jobs(jobs: list[dict], max_age_days: int = 3) -> list[dict]:
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
            result.append(job)  # No date → keep it
            continue

        parsed = _parse_posted_date(posted)
        if parsed is None:
            result.append(job)  # Unparseable → keep it
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
    match = re.match(r"(\d+)\s+(hour|day|week|month)s?\s+ago", date_str.strip(), re.IGNORECASE)
    if match:
        n = int(match.group(1))
        unit = match.group(2).lower()
        delta_map = {"hour": timedelta(hours=n), "day": timedelta(days=n),
                     "week": timedelta(weeks=n), "month": timedelta(days=n * 30)}
        return datetime.now(timezone.utc) - delta_map.get(unit, timedelta())

    return None


# =============================================================================
# Notification — GitHub Issue
# =============================================================================

def format_issue_body(all_new_jobs: list[tuple[dict, list[dict]]]) -> str:
    """Format the GitHub Issue body as Markdown."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_new = sum(len(jobs) for _, jobs in all_new_jobs)
    total_companies = len(all_new_jobs)

    lines = [
        "# 🆕 New Positions Found\n",
        f"**Date:** {now}  ",
        f"**Companies with new positions:** {total_companies}  ",
        f"**Total new positions:** {total_new}\n",
        "---\n",
    ]

    for company, jobs in all_new_jobs:
        ats_label = company["ats"].capitalize()
        lines.append(f"## {company['name']} ({ats_label})\n")

        # Build table header based on available fields
        has_department = any(job.get("department") for job in jobs)
        if has_department:
            lines.append("| Title | Department | Location | Posted | Link |")
            lines.append("|-------|------------|----------|--------|------|")
        else:
            lines.append("| Title | Location | Posted | Link |")
            lines.append("|-------|----------|--------|------|")

        for job in jobs:
            title = job["title"]
            location = job.get("location", "N/A") or "N/A"
            posted = job.get("posted_date", "N/A") or "N/A"
            if posted and posted != "N/A":
                # Extract just the date part
                posted = posted[:10]
            url = job.get("url", "")
            link = f"[Apply]({url})" if url else "N/A"

            if has_department:
                dept = job.get("department", "N/A") or "N/A"
                lines.append(f"| {title} | {dept} | {location} | {posted} | {link} |")
            else:
                lines.append(f"| {title} | {location} | {posted} | {link} |")

        lines.append("")

    lines.append("---")
    lines.append("*Generated by [NewPositionMonitor](https://github.com/kunli-li/NewPositionMonitor)*")

    return "\n".join(lines)


def create_github_issue(all_new_jobs: list[tuple[dict, list[dict]]]) -> None:
    """Create a GitHub Issue with new positions summary."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")

    body = format_issue_body(all_new_jobs)

    if not token or not repo:
        print("\n--- GitHub Issue Preview (GITHUB_TOKEN not set) ---")
        print(body)
        print("--- End Preview ---\n")
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = f"🆕 New Marketing Intern Positions - {now}"

    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "title": title,
        "body": body,
        "labels": ["new-positions"],
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        issue_url = resp.json().get("html_url", "")
        print(f"✅ GitHub Issue created: {issue_url}")
    except requests.RequestException as e:
        print(f"⚠️  Failed to create GitHub Issue: {e}")
        print("Falling back to stdout:")
        print(body)


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Monitor job positions from ATS APIs")
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Seed mode: save snapshots without sending notifications",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: companies.yaml)",
    )
    args = parser.parse_args()

    # Load config
    config = load_config(args.config)
    filters = config.get("filters")
    companies = config["companies"]

    print(f"📋 Monitoring {len(companies)} companies...")
    if args.seed:
        print("🌱 Seed mode: saving snapshots only, no notifications.")

    all_new_jobs: list[tuple[dict, list[dict]]] = []

    for company in companies:
        name = company["name"]
        print(f"\n--- {name} ({company['ats']}/{company['slug']}) ---")

        # Fetch current jobs
        try:
            current_jobs = fetch_jobs(company)
            print(f"  Fetched {len(current_jobs)} total jobs")
        except requests.RequestException as e:
            print(f"  ⚠️  Failed to fetch: {e}")
            continue

        # Apply filters
        filtered_jobs = apply_filters(current_jobs, filters)
        print(f"  After filtering: {len(filtered_jobs)} matching jobs")

        # Load previous snapshot and find new jobs
        previous_jobs = load_snapshot(company)
        new_jobs = find_new_jobs(previous_jobs, filtered_jobs)

        # Only notify about jobs posted within the last 3 days
        new_jobs = filter_recent_jobs(new_jobs, max_age_days=3)
        print(f"  New positions (last 3 days): {len(new_jobs)}")

        if new_jobs:
            for job in new_jobs:
                print(f"    + {job['title']} ({job.get('location', 'N/A')})")
            all_new_jobs.append((company, new_jobs))

        # Save current snapshot (filtered jobs only)
        save_snapshot(company, filtered_jobs)

    # Summary
    print(f"\n{'='*50}")
    total_new = sum(len(jobs) for _, jobs in all_new_jobs)
    print(f"📊 Total new positions found: {total_new}")

    # Send notification (unless seed mode)
    if all_new_jobs and not args.seed:
        create_github_issue(all_new_jobs)
    elif args.seed:
        print("🌱 Seed mode: skipping notification.")
    else:
        print("✅ No new positions found. No notification sent.")


if __name__ == "__main__":
    main()
