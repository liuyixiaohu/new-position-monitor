"""ATS fetchers — each returns a list of normalized Job dicts.

Supports: Greenhouse, Lever, Ashby, Amazon, Workday,
SmartRecruiters, Phenom, iCIMS, SerpApi.
"""

from __future__ import annotations

import json
import os
import re
import time

import requests

from config import REQUEST_TIMEOUT
from models import Job

# --- Retry config for transient failures ---
_MAX_RETRIES = 1
_RETRY_BACKOFF = 2.0  # seconds


def _get_with_retry(url: str, **kwargs) -> requests.Response:
    """GET with one retry on transient failures (5xx, timeout, connection)."""
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = requests.get(url, **kwargs)
            resp.raise_for_status()
            return resp
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < _MAX_RETRIES:
                print(f"    Retry after transient error: {e}")
                time.sleep(_RETRY_BACKOFF)
            else:
                raise
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status >= 500 and attempt < _MAX_RETRIES:
                print(f"    Retry after server error {status}")
                time.sleep(_RETRY_BACKOFF)
            else:
                raise
    raise RuntimeError("unreachable")


def _post_with_retry(url: str, **kwargs) -> requests.Response:
    """POST with one retry on transient failures."""
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = requests.post(url, **kwargs)
            resp.raise_for_status()
            return resp
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < _MAX_RETRIES:
                print(f"    Retry after transient error: {e}")
                time.sleep(_RETRY_BACKOFF)
            else:
                raise
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status >= 500 and attempt < _MAX_RETRIES:
                print(f"    Retry after server error {status}")
                time.sleep(_RETRY_BACKOFF)
            else:
                raise
    raise RuntimeError("unreachable")


# =============================================================================
# Dispatcher
# =============================================================================


def fetch_jobs(company: dict) -> list[Job]:
    """Dispatch to the correct ATS fetcher."""
    ats = company["ats"]
    slug = company["slug"]

    dispatchers = {
        "greenhouse": lambda: fetch_greenhouse(slug),
        "lever": lambda: fetch_lever(slug),
        "ashby": lambda: fetch_ashby(slug),
        "amazon": lambda: fetch_amazon(),
        "workday": lambda: fetch_workday(company),
        "smartrecruiters": lambda: fetch_smartrecruiters(slug),
        "phenom": lambda: fetch_phenom(company),
        "icims": lambda: fetch_icims(company),
        "serpapi": lambda: fetch_serpapi(company),
    }

    fetcher = dispatchers.get(ats)
    if not fetcher:
        raise ValueError(f"Unknown ATS type: {ats}")
    return fetcher()


# =============================================================================
# Individual fetchers
# =============================================================================


def fetch_greenhouse(slug: str) -> list[Job]:
    """Fetch jobs from Greenhouse public API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    data = _get_with_retry(url).json()

    return [
        Job(
            id=str(job.get("id", "")),
            title=job.get("title", ""),
            location=job.get("location", {}).get("name", ""),
            department=None,
            url=job.get("absolute_url", ""),
            posted_date=job.get("first_published", ""),
            updated_at=job.get("updated_at", ""),
        )
        for job in data.get("jobs", [])
    ]


def fetch_lever(slug: str) -> list[Job]:
    """Fetch jobs from Lever public API."""
    from datetime import datetime, timezone

    data = _get_with_retry(
        f"https://api.lever.co/v0/postings/{slug}?mode=json"
    ).json()

    jobs = []
    for job in (data if isinstance(data, list) else []):
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
        jobs.append(
            Job(
                id=str(job.get("id", "")),
                title=job.get("text", ""),
                location=categories.get("location", ""),
                department=categories.get("department", ""),
                url=job.get("hostedUrl", ""),
                posted_date=posted_date,
                updated_at="",
            )
        )
    return jobs


def fetch_ashby(slug: str) -> list[Job]:
    """Fetch jobs from Ashby public API."""
    data = _get_with_retry(
        f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
        params={"includeCompensation": "true"},
    ).json()

    return [
        Job(
            id=str(job.get("id", "")),
            title=job.get("title", ""),
            location=job.get("location", ""),
            department=job.get("department", ""),
            url=job.get("jobUrl", ""),
            posted_date=job.get("publishedAt", ""),
            updated_at="",
        )
        for job in data.get("jobs", [])
    ]


def fetch_amazon() -> list[Job]:
    """Fetch jobs from Amazon's public search API. Paginates through all results."""
    base_url = "https://www.amazon.jobs/en/search.json"
    all_jobs: list[Job] = []
    offset = 0
    page_size = 100

    while offset < 10000:
        params = {
            "offset": offset,
            "result_limit": page_size,
            "sort": "recent",
            "country": "USA",
        }
        data = _get_with_retry(base_url, params=params).json()

        hits = data.get("jobs", [])
        if not hits:
            break

        for job in hits:
            job_id = job.get("id_icims") or job.get("id") or ""
            all_jobs.append(
                Job(
                    id=str(job_id),
                    title=job.get("title", ""),
                    location=job.get("normalized_location", job.get("location", "")),
                    department=job.get("job_category", ""),
                    url=f"https://www.amazon.jobs{job.get('job_path', '')}",
                    posted_date=job.get("posted_date", ""),
                    updated_at=job.get("updated_time", ""),
                )
            )

        if len(hits) < page_size:
            break
        offset += page_size

    return all_jobs


def fetch_workday(company: dict) -> list[Job]:
    """Fetch jobs from Workday's undocumented public API.

    NOTE: This is NOT an official API. It could break at any time.
    """
    slug = company["slug"]
    site = company.get("workday_site", "External")
    instance = company.get("workday_instance", "wd1")

    base_url = (
        f"https://{slug}.{instance}.myworkdayjobs.com"
        f"/wday/cxs/{slug}/{site}/jobs"
    )

    all_jobs: list[Job] = []
    offset = 0
    page_size = 20

    while offset < 10000:
        payload = {"limit": page_size, "offset": offset, "searchText": ""}
        data = _post_with_retry(
            base_url, json=payload, headers={"Content-Type": "application/json"}
        ).json()

        postings = data.get("jobPostings", [])
        if not postings:
            break

        for job in postings:
            external_path = job.get("externalPath", "")
            job_url = (
                f"https://{slug}.{instance}.myworkdayjobs.com{external_path}"
                if external_path
                else ""
            )

            location_list = job.get("locationsText", "")
            bullet_fields = job.get("bulletFields", [])
            if not location_list and bullet_fields:
                location_list = " | ".join(bullet_fields)

            # Use externalPath as stable ID; fall back to title slug
            job_id = external_path or job.get("title", "unknown")

            all_jobs.append(
                Job(
                    id=str(job_id),
                    title=job.get("title", ""),
                    location=location_list,
                    department="",
                    url=job_url,
                    posted_date=job.get("postedOn", ""),
                    updated_at="",
                )
            )

        total = data.get("total", 0)
        offset += page_size
        if offset >= total:
            break

    return all_jobs


def fetch_smartrecruiters(slug: str) -> list[Job]:
    """Fetch jobs from SmartRecruiters public API."""
    base_url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    all_jobs: list[Job] = []
    offset = 0
    page_size = 100

    while offset < 10000:
        data = _get_with_retry(
            base_url, params={"offset": offset, "limit": page_size}
        ).json()

        postings = data.get("content", [])
        if not postings:
            break

        for job in postings:
            location = job.get("location", {})
            location_str = location.get("fullLocation", "")
            if not location_str:
                parts = [
                    location.get("city", ""),
                    location.get("region", ""),
                    location.get("country", ""),
                ]
                location_str = ", ".join(p for p in parts if p)

            dept = job.get("department", {})
            dept_name = dept.get("label", "") if isinstance(dept, dict) else ""

            all_jobs.append(
                Job(
                    id=str(job.get("id", "")),
                    title=job.get("name", ""),
                    location=location_str,
                    department=dept_name,
                    url=job.get("ref", ""),
                    posted_date=job.get("releasedDate", ""),
                    updated_at="",
                )
            )

        total = data.get("totalFound", 0)
        offset += page_size
        if offset >= total:
            break

    return all_jobs


def fetch_phenom(company: dict) -> list[Job]:
    """Fetch jobs from Phenom-powered career sites by parsing embedded JSON.

    Phenom renders job data server-side in a phApp.ddo JavaScript variable.
    This is HTML parsing — more fragile than API calls.
    """
    phenom_url = company.get("phenom_url", "")
    if not phenom_url:
        print(f"  Warning: No phenom_url configured for {company['name']}")
        return []

    all_jobs: list[Job] = []
    offset = 0

    while offset < 10000:
        url = f"{phenom_url}?from={offset}&s=1"
        resp = _get_with_retry(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html",
            },
        )
        content = resp.text

        match = re.search(r"phApp\.ddo\s*=\s*", content)
        if not match:
            print("  Warning: Could not find phApp.ddo in page")
            break

        start = match.end()
        depth = 0
        end = start
        for i in range(start, min(start + 500000, len(content))):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        try:
            data = json.loads(content[start:end])
        except json.JSONDecodeError:
            print("  Warning: Failed to parse phApp.ddo JSON")
            break

        search_data = data.get("eagerLoadRefineSearch", {}).get("data", {})
        raw_jobs = search_data.get("jobs", [])
        if not raw_jobs:
            break

        for job in raw_jobs:
            location_str = job.get("cityStateCountry", "")
            if not location_str:
                parts = [job.get("city", ""), job.get("state", ""), job.get("country", "")]
                location_str = ", ".join(p for p in parts if p)

            all_jobs.append(
                Job(
                    id=str(job.get("jobId", "")),
                    title=job.get("title", ""),
                    location=location_str,
                    department=job.get("category", ""),
                    url=job.get("applyUrl", ""),
                    posted_date=job.get("postedDate", ""),
                    updated_at=job.get("dateCreated", ""),
                )
            )

        offset += len(raw_jobs)
        if len(raw_jobs) < 10:
            break

    return all_jobs


def fetch_icims(company: dict) -> list[Job]:
    """Fetch jobs from iCIMS-powered career sites (e.g., Rivian)."""
    icims_url = company.get("icims_url", "")
    if not icims_url:
        print(f"  Warning: No icims_url configured for {company['name']}")
        return []

    all_jobs: list[Job] = []
    offset = 0
    page_size = 100

    while offset < 10000:
        data = _get_with_retry(
            icims_url, params={"offset": offset, "limit": page_size}
        ).json()

        postings = data.get("jobs", [])
        if not postings:
            break

        for job in postings:
            job_data = job.get("data", {})
            categories = job_data.get("categories", [])
            dept = categories[0].get("name", "") if categories else ""

            all_jobs.append(
                Job(
                    id=str(job_data.get("slug", "")),
                    title=job_data.get("title", ""),
                    location=job_data.get("location_name", ""),
                    department=dept,
                    url=job_data.get("apply_url", ""),
                    posted_date=job_data.get("posted_date", ""),
                    updated_at=job_data.get("update_date", ""),
                )
            )

        total = data.get("totalCount", 0)
        offset += page_size
        if offset >= total:
            break

    return all_jobs


def fetch_serpapi(company: dict) -> list[Job]:
    """Fetch jobs via SerpApi's Google Jobs API.

    Used for companies with no direct ATS API (e.g., Tesla).
    Requires SERPAPI_KEY environment variable.
    """
    api_key = os.environ.get("SERPAPI_KEY", "")
    if not api_key:
        print(f"  Warning: SERPAPI_KEY not set, skipping {company['name']}")
        return []

    query = company.get("serpapi_query", "")
    if not query:
        print(f"  Warning: No serpapi_query configured for {company['name']}")
        return []

    all_jobs: list[Job] = []
    start = 0

    while True:
        params: dict = {
            "engine": "google_jobs",
            "q": query,
            "api_key": api_key,
            "start": start,
        }
        gl = company.get("serpapi_gl", "us")
        if gl:
            params["gl"] = gl

        data = _get_with_retry("https://serpapi.com/search", params=params).json()

        raw_jobs = data.get("jobs_results", [])
        if not raw_jobs:
            break

        for job in raw_jobs:
            apply_options = job.get("apply_options", [])
            apply_url = apply_options[0].get("link", "") if apply_options else ""

            all_jobs.append(
                Job(
                    id=str(job.get("job_id", "")),
                    title=job.get("title", ""),
                    location=job.get("location", ""),
                    department=job.get("company_name", ""),
                    url=apply_url,
                    posted_date=job.get("detected_extensions", {}).get("posted_at", ""),
                    updated_at="",
                )
            )

        start += 10
        if start >= 20:  # Conservative: max 2 pages per company
            break

    return all_jobs
