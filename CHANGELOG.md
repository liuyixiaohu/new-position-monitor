# Changelog

## v2.1 (2026-03-01)

### Improved
- Only notify about jobs posted within the last 3 days, filtering out old positions that appear as "new" due to API result fluctuations
- Multi-format date parser supporting ISO 8601, "Month DD, YYYY" (Amazon), and relative dates like "2 days ago" (SerpApi)

## v2.0 (2026-02-24)

### Added
- **10 new companies** (total: 18 monitored)
  - Anduril Industries (Greenhouse)
  - Amazon (custom JSON API)
  - Intel, Boston Dynamics, NVIDIA, Rockwell Automation (Workday)
  - Intuitive Surgical (SmartRecruiters)
  - Adobe (Phenom)
  - Rivian (iCIMS)
  - Tesla (SerpApi / Google Jobs)
- **6 new ATS integrations**: Workday, Amazon, SmartRecruiters, Phenom, iCIMS, SerpApi
- US location filter (location_keywords group) for three-group AND filtering
- `.gitignore` for `__pycache__/`

### Fixed
- "intern" keyword no longer matches "International" (word boundary regex)
- Rockwell Automation Workday site name corrected to `External_Rockwell_Automation`
- Adobe Phenom JSON extraction using brace-depth counting instead of simple regex

### Changed
- Daily run time changed from 6AM PST to **8PM PST** (4AM UTC)

## v1.0 (2026-02-24)

### Added
- Initial release with **8 companies** monitored via Greenhouse (×7) and Ashby (×1)
  - Airbnb, Waymo, Nuro, Lucid Motors, Agility Robotics, Locus Robotics, Fetch Robotics, Figure AI
- Three-group AND keyword filtering (intern_keywords + role_keywords)
- Snapshot-based diff detection (by job ID)
- GitHub Actions daily cron workflow
- GitHub Issue notifications with markdown tables
- `--seed` mode for initial snapshot without notifications
- Manual workflow trigger via GitHub Actions UI
