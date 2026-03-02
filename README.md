# Colare Lead Scout

Automatically discovers hardtech hiring signals across LinkedIn, X/Twitter, Reddit, and Hacker News — then scores and ranks each post as a potential enterprise lead for [Colare](https://www.colare.com).

## What It Does

1. **Searches** 4 platforms for posts about hardtech hiring pain, scaling engineering teams, open roles, and assessment frustration
2. **Scores** each result on 3 axes: Title Fit, Company Fit, and Intent Signal (0–10 each)
3. **Grades** leads A through F based on a weighted composite score
4. **Publishes** qualified leads to a Notion database for tracking and outreach

## How Scoring Works

Each lead is scored on 3 axes:

| Axis | What It Measures | Weight |
|------|-----------------|--------|
| **Title Fit** | Is this person a hiring decision-maker? (VP Eng, Head of Talent, etc.) | 25% |
| **Company Fit** | Is this a hardtech company? (aerospace, robotics, defense, EV, etc.) | 25% |
| **Intent Signal** | Are they actively hiring or struggling to hire? | 50% |

Signal categories also carry multipliers:
- **Hiring Pain** (3x) — "can't find engineers", "hiring is broken"
- **Assessment Frustration** (3x) — "technical assessment doesn't work"
- **Scaling Engineering** (2x) — "doubling our team", "Series B hiring"
- **Open Hardtech Roles** (2x) — "hiring mechanical engineer"
- **Industry Momentum** (1x) — "defense tech hiring boom"

Grades: **A** (8+) → **B** (6+) → **C** (4+) → **D** (2+) → **F** (<2)

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/NaveenChandraSanka/colare-leads.git
cd colare-leads
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Set up environment variables

Create a `.env` file:

```bash
# Notion integration token
# Create one at: https://www.notion.so/my-integrations
NOTION_TOKEN=your_notion_token_here

# Notion database ID (from the database URL)
NOTION_DATABASE_ID=your_database_id_here
```

### 3. Set up the Notion database

Create a Notion database with these properties:

| Property | Type | Description |
|----------|------|-------------|
| Name | Title | Auto-filled with grade + author |
| Author | Rich text | Post creator |
| Lead Score | Number | Composite score (0–10) |
| Grade | Select | A / B / C / D / F |
| Signal | Rich text | Signal category |
| Platform | Select | LinkedIn, Twitter/X, Reddit, Web |
| Title Fit | Number | Title axis score (0–10) |
| Company Fit | Number | Company axis score (0–10) |
| Intent Signal | Number | Intent axis score (0–10) |
| Verticals | Multi-select | Matched hardtech verticals |
| Link | URL | Direct link to the post |
| Snippet | Rich text | Post preview |
| Keyword | Rich text | Search keyword that found it |
| Scraped At | Date | Date the lead was found |
| Contacted | Checkbox | For tracking outreach |
| Notes | Rich text | For outreach notes |

Then connect your Notion integration to the database:
1. Open the database in Notion
2. Click **...** (top right) → **Connections** → Add your integration

### 4. Run it

```bash
# Recommended: use run.sh (auto-loads .env and activates venv)
chmod +x run.sh

# Dry run — search + score, print to terminal (no publishing)
./run.sh --dry-run

# Full run — search, score, and publish grade C+ leads to Notion
./run.sh --min-grade C

# Save a local markdown report
./run.sh --markdown

# Run on a weekly schedule
./run.sh --schedule
```

> **Important:** Always use `./run.sh` instead of `python main.py` directly. The run script automatically loads your `.env` secrets and activates the virtual environment. Running `python main.py` directly will fail because the environment variables won't be set.

## Configuration

Edit `config.yaml` to customize:

- **Signal keywords** — what hiring pain signals to search for
- **Tracked companies** — hardtech companies to monitor (Anduril, Rivian, Shield AI, etc.)
- **Tracked people** — hiring leaders and founders to follow
- **Scoring weights** — title keywords, company verticals, intent signals
- **Search settings** — days to look back, max results, which platforms to search
- **Reddit subreddits** — which engineering subreddits to scan

## Project Structure

```
colare-leads/
├── main.py               # CLI entry point
├── search.py             # Multi-platform search engine
├── scoring.py            # 3-axis lead scoring model
├── notion_publisher.py   # Notion database integration
├── config.yaml           # All configuration (keywords, companies, scoring)
├── requirements.txt      # Python dependencies
├── run.sh                # Shell script runner
└── .env                  # Secrets (not committed)
```

## Dependencies

- **ddgs** — DuckDuckGo search (free, no API keys needed)
- **notion-client** — Notion API
- **pyyaml** — Config parsing
- **requests** — Hacker News Algolia API
- **schedule** — Weekly scheduling

No paid APIs required. All searches use DuckDuckGo (free) and the HN Algolia API (free).
