"""Config loading and validation."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

CONFIG_FILE = Path(__file__).parent.parent / "companies.yaml"
DATA_DIR = Path(__file__).parent.parent / "data"
REQUEST_TIMEOUT = 30  # seconds

VALID_ATS_TYPES = frozenset({
    "greenhouse", "lever", "ashby", "amazon", "workday",
    "smartrecruiters", "phenom", "icims", "serpapi",
})


def load_config(path: str | None = None) -> dict:
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
        if company["ats"] not in VALID_ATS_TYPES:
            print(f"ERROR: Unknown ATS type '{company['ats']}' for {company['name']}")
            sys.exit(1)

    return config
