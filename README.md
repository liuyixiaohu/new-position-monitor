# NewPositionMonitor

Monitor target companies for new job positions via their ATS (Applicant Tracking System) public APIs. Runs daily on GitHub Actions and creates a GitHub Issue when new matching positions are found.

## How It Works

1. **Fetches** job listings from multiple ATS public APIs (Greenhouse, Ashby, Workday, SmartRecruiters, Phenom, Amazon)
2. **Filters** by keywords (e.g., "intern" + "marketing" + US location)
3. **Compares** against previous snapshots stored in `data/`
4. **Notifies** via GitHub Issue when new positions appear
5. **Commits** updated snapshots back to the repo

## Quick Start

### 1. Configure your target companies

Edit `companies.yaml` to add/remove companies:

```yaml
companies:
  - name: Waymo
    ats: greenhouse      # greenhouse, lever, ashby, workday, amazon, smartrecruiters, phenom
    slug: waymo          # company identifier in ATS URL
```

### 2. Configure filters

```yaml
filters:
  intern_keywords:       # Must match at least one (AND with role_keywords)
    - "intern"
  role_keywords:         # Must match at least one
    - "marketing"
    - "product marketing"
  location_keywords:     # Must match at least one (location field)
    - "United States"
    - ", CA"
    - "Remote"
  case_sensitive: false
```

### 3. First run (seed mode)

Seed mode saves snapshots without sending notifications — prevents a massive "everything is new" issue:

```bash
# Locally
pip install -r requirements.txt
python monitor.py --seed

# Or via GitHub Actions
# Go to Actions tab → "Monitor Job Positions" → Run workflow → Check "Seed mode"
```

### 4. Daily monitoring

After seeding, the workflow runs automatically every day at 8PM PST. You'll receive a GitHub Issue whenever new matching positions are found.

You can also trigger manually: **Actions tab → "Monitor Job Positions" → Run workflow**.

## Supported ATS Systems

| ATS | API Endpoint | Auth | Notes |
|-----|-------------|------|-------|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{slug}/jobs` | No | Official public API |
| Lever | `api.lever.co/v0/postings/{slug}?mode=json` | No | Official public API |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{slug}` | No | Official public API |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/{slug}/postings` | No | Official public API |
| Amazon | `amazon.jobs/en/search.json` | No | Custom API |
| Workday | `{slug}.{instance}.myworkdayjobs.com/wday/cxs/{slug}/{site}/jobs` | No | Undocumented, may break |
| Phenom | Embedded JSON in career page HTML | No | HTML parsing, may break |

### Finding a company's ATS slug

- **Greenhouse**: Look at `boards.greenhouse.io/{slug}` in their careers page URL
- **Lever**: Look at `jobs.lever.co/{slug}` in their careers page URL
- **Ashby**: Look at `jobs.ashbyhq.com/{slug}` in their careers page URL
- **SmartRecruiters**: Look at `jobs.smartrecruiters.com/{slug}` in their careers page URL

## Currently Monitored Companies

| Company | ATS | Status |
|---------|-----|--------|
| Airbnb | Greenhouse | ✅ Monitored |
| Waymo | Greenhouse | ✅ Monitored |
| Nuro | Greenhouse | ✅ Monitored |
| Lucid Motors | Greenhouse | ✅ Monitored |
| Agility Robotics | Greenhouse | ✅ Monitored |
| Locus Robotics | Greenhouse | ✅ Monitored |
| Fetch Robotics | Greenhouse | ✅ Monitored |
| Anduril Industries | Greenhouse | ✅ Monitored |
| Figure AI | Ashby | ✅ Monitored |
| Amazon | Custom API | ✅ Monitored |
| Intel | Workday | ✅ Monitored |
| Boston Dynamics | Workday | ✅ Monitored |
| NVIDIA | Workday | ✅ Monitored |
| Rockwell Automation | Workday | ✅ Monitored |
| Intuitive Surgical | SmartRecruiters | ✅ Monitored |
| Adobe | Phenom | ✅ Monitored |

### Companies Not Yet Supported

| Company | ATS | Issue |
|---------|-----|-------|
| Google | Custom (rp2talent) | Proprietary system |
| Microsoft | Eightfold | No public API, SPA rendering |
| Qualcomm | Eightfold | No public API |
| Tesla | Unknown | Blocked by CDN |
| TikTok/ByteDance | Custom (Feishu) | Proprietary system |
| Rivian | iCIMS | Requires HTML parsing |
| Teradyne | SAP SuccessFactors | No public API |
| Cruise | Shut down | Defunct, redirects to GM |

## Project Structure

```
├── .github/workflows/monitor.yml   # GitHub Actions daily cron (8PM PST)
├── data/                            # Job snapshots (auto-managed)
├── companies.yaml                   # Your target companies + filters
├── monitor.py                       # Main script
├── requirements.txt                 # Python dependencies
└── README.md
```
