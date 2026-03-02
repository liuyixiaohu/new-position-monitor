"""Orchestrator for the NewPositionMonitor pipeline."""

from __future__ import annotations

import argparse

import requests

from config import load_config
from differ import filter_recent_jobs, find_new_jobs
from fetchers import fetch_jobs
from filters import apply_filters
from models import Job
from notifier import notify
from snapshot import load_snapshot, save_snapshot


def main() -> None:
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

    config = load_config(args.config)
    filters = config.get("filters")
    companies = config["companies"]

    print(f"Monitoring {len(companies)} companies...")
    if args.seed:
        print("Seed mode: saving snapshots only, no notifications.")

    all_new_jobs: list[tuple[dict, list[Job]]] = []

    for company in companies:
        name = company["name"]
        print(f"\n--- {name} ({company['ats']}/{company['slug']}) ---")

        # Fetch
        try:
            current_jobs = fetch_jobs(company)
            print(f"  Fetched {len(current_jobs)} total jobs")
        except requests.RequestException as e:
            print(f"  Failed to fetch: {e}")
            continue

        # Filter
        filtered_jobs = apply_filters(current_jobs, filters)
        print(f"  After filtering: {len(filtered_jobs)} matching jobs")

        # Diff
        previous_jobs = load_snapshot(company)
        new_jobs = find_new_jobs(previous_jobs, filtered_jobs)
        new_jobs = filter_recent_jobs(new_jobs, max_age_days=3)
        print(f"  New positions (last 3 days): {len(new_jobs)}")

        if new_jobs:
            for job in new_jobs:
                print(f"    + {job['title']} ({job.get('location', 'N/A')})")
            all_new_jobs.append((company, new_jobs))

        # Save
        save_snapshot(company, filtered_jobs)

    # Summary
    print(f"\n{'=' * 50}")
    total_new = sum(len(jobs) for _, jobs in all_new_jobs)
    print(f"Total new positions found: {total_new}")

    # Notify
    if all_new_jobs and not args.seed:
        notify(all_new_jobs, filters=filters)
    elif args.seed:
        print("Seed mode: skipping notification.")
    else:
        print("No new positions found. No notification sent.")


if __name__ == "__main__":
    main()
