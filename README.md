# Job Position Monitor

**Automatically track new job openings at companies you care about — get notified daily via GitHub.**

Tired of manually refreshing career pages every day? This tool checks them for you. It monitors the job boards of your target companies, filters by keywords (e.g., "intern" + "marketing"), and creates a GitHub notification whenever new matching positions appear.

## How It Works

```
  ┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌───────────────┐
  │  Every day   │────▶│  Fetch jobs   │────▶│  Filter by   │────▶│  Compare with │
  │  (automatic) │     │  from career  │     │  keywords &  │     │  yesterday    │
  └─────────────┘     │  pages        │     │  location    │     └──────┬────────┘
                      └──────────────┘     └──────────────┘            │
                                                                  New jobs?
                                                               Yes │      │ No
                                                          ┌────────▼──┐   │
                                                          │  Create   │   │ Done, wait
                                                          │  GitHub   │   │ until
                                                          │  Issue    │   │ tomorrow
                                                          └───────────┘   │
```

1. A scheduled job runs every day at 8 PM PST
2. It fetches job listings from each company's career page API
3. It filters results by your keywords (role type, department, location)
4. It compares against the previous day's snapshot
5. If new matching jobs are found, it creates a GitHub Issue with direct apply links

## What a Notification Looks Like

When new jobs are found, you'll get a GitHub Issue like this:

> **New Intern Marketing Positions — 2025-06-15**
>
> **Companies with new positions:** 3
> **Total new positions:** 7
>
> ### Waymo (Greenhouse)
> | Title | Location | Posted | Link |
> |-------|----------|--------|------|
> | Marketing Intern, Summer 2025 | Mountain View, CA | 2025-06-14 | [Apply](https://...) |
>
> ### NVIDIA (Workday)
> | Title | Department | Location | Posted | Link |
> |-------|------------|----------|--------|------|
> | Product Marketing Intern | Marketing | Santa Clara, CA | 2025-06-13 | [Apply](https://...) |

## Currently Monitored Companies

| Company | Career Page System |
|---------|-------------------|
| Airbnb, Waymo, Nuro, Lucid Motors, Agility Robotics, Locus Robotics, Fetch Robotics, Anduril Industries | Greenhouse |
| Figure AI | Ashby |
| Amazon | Custom career API |
| Intel, Boston Dynamics, NVIDIA, Rockwell Automation | Workday |
| Intuitive Surgical | SmartRecruiters |
| Adobe | Phenom |
| Rivian | iCIMS |
| Tesla | Google Jobs (via SerpApi) |

> Some companies (Google, Microsoft, Qualcomm, TikTok) use proprietary career systems that don't have public APIs. These are not currently supported.

## Set Up Your Own

### 1. Fork this repo

Click the **Fork** button at the top right of this page.

### 2. Add your target companies

Edit `companies.yaml` to list the companies you want to monitor:

```yaml
companies:
  - name: Waymo              # Company name (for display)
    ats: greenhouse           # Which career page system they use (see table below)
    slug: waymo               # The company's ID in their career page URL
```

**How to find a company's slug:** Go to their careers page. The URL usually looks like `jobs.greenhouse.io/waymo` or `jobs.lever.co/stripe` — the last part is the slug.

### 3. Set your filters

In the same `companies.yaml`, define what jobs you're looking for:

```yaml
filters:
  intern_keywords:            # Job must contain one of these...
    - "intern"
  role_keywords:              # ...AND one of these
    - "marketing"
    - "product marketing"
  location_keywords:          # ...AND be in one of these locations
    - "United States"
    - ", CA"
    - "Remote"
  case_sensitive: false       # Ignore uppercase/lowercase
```

### 4. Run the first time (seed mode)

The first run saves a snapshot of current jobs without sending notifications — otherwise you'd get a massive "everything is new" alert:

```bash
# On your computer
pip install -r requirements.txt
python monitor.py --seed

# Or via GitHub Actions
# Go to Actions tab → "Monitor Job Positions" → Run workflow → Check "Seed mode"
```

### 5. Daily monitoring

After seeding, the workflow runs automatically every day at 8 PM PST. You'll get a GitHub Issue whenever new matching positions appear.

You can also trigger manually: **Actions** → **Monitor Job Positions** → **Run workflow**.

To get email notifications, make sure you're **Watching** your fork (click the **Watch** button → **All Activity**).

## Supported Career Page Systems

This tool works with 9 different career page systems (called ATS — Applicant Tracking Systems). Most major tech companies use one of these:

| System | How It Works | Notes |
|--------|-------------|-------|
| Greenhouse | Official public API | Most reliable |
| Lever | Official public API | Most reliable |
| Ashby | Official public API | Most reliable |
| SmartRecruiters | Official public API | Most reliable |
| iCIMS | Public JSON API | Reliable |
| Amazon | Custom career API | Reliable |
| SerpApi | Searches Google Jobs | Free tier: 100 searches/month |
| Workday | Undocumented API | Works but may break with updates |
| Phenom | Reads career page HTML | Works but may break with updates |

### Finding which system a company uses

Visit the company's careers page and look at the URL:
- `boards.greenhouse.io/company` → Greenhouse
- `jobs.lever.co/company` → Lever
- `jobs.ashbyhq.com/company` → Ashby
- `jobs.smartrecruiters.com/company` → SmartRecruiters
- `company.wd1.myworkdayjobs.com` → Workday

## Project Structure

```
├── .github/workflows/monitor.yml   # Scheduled job (runs daily at 8 PM PST)
├── companies.yaml                   # Your target companies + keyword filters
├── monitor.py                       # Entry point (delegates to src/)
├── data/                            # Job snapshots (auto-managed)
├── src/
│   ├── main.py                      # Orchestrator — runs the whole pipeline
│   ├── fetchers.py                  # Talks to each career page API
│   ├── filters.py                   # Applies keyword + location filters
│   ├── differ.py                    # Finds what's new vs. yesterday
│   ├── snapshot.py                  # Saves/loads daily snapshots
│   ├── notifier.py                  # Creates GitHub Issues
│   ├── config.py                    # Reads companies.yaml
│   └── models.py                    # Data structure definitions
└── requirements.txt                 # Python packages needed
```

## License

MIT
