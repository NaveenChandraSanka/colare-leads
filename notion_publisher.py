"""
Notion publisher — writes scored leads as rows in a Colare Leads database.

Notion Database Schema (create this in Notion first):
  - Name (title)           → Lead grade + author name
  - Author (rich_text)     → Creator / poster name
  - Lead Score (number)    → Composite score 0-10
  - Grade (select)         → A / B / C / D / F
  - Signal (select)        → "Hiring Pain", "Scaling Engineering", etc.
  - Platform (select)      → "LinkedIn", "X", "Reddit", "Hacker News"
  - Title Fit (number)     → Title axis score 0-10
  - Company Fit (number)   → Company axis score 0-10
  - Intent Signal (number) → Intent axis score 0-10
  - Verticals (multi_select) → Matched company verticals
  - Link (url)             → Direct link to the post
  - Snippet (rich_text)    → Post preview text
  - Keyword (rich_text)    → Search keyword that found this
  - Scraped At (date)      → Today's date
  - Contacted (checkbox)   → Unchecked by default (check when you reach out)
  - Notes (rich_text)      → Empty, for outreach notes
"""

import os
import logging
from datetime import datetime

from notion_client import Client

from scoring import ScoredLead

logger = logging.getLogger(__name__)

# Grade labels for Notion select
GRADE_LABELS = {
    "A": "🔥 A — Hot",
    "B": "🟢 B — Strong",
    "C": "🟡 C — Warm",
    "D": "⚪ D — Weak",
    "F": "❌ F — Low",
}

# Grade colors for Notion select
GRADE_COLORS = {
    "A": "red",
    "B": "green",
    "C": "yellow",
    "D": "default",
    "F": "gray",
}

PLATFORM_MAP = {
    "linkedin": "LinkedIn",
    "twitter": "Twitter/X",
    "reddit": "Reddit",
    "hackernews": "Web",  # No HN option in Notion DB; closest is "Web"
}

SIGNAL_COLORS = {
    "Hiring Pain": "red",
    "Scaling Engineering": "orange",
    "Open Hardtech Roles": "blue",
    "Assessment Frustration": "purple",
    "Industry Momentum": "green",
    "Tracked Company": "pink",
    "Tracked Person": "brown",
    "Community Discussion": "yellow",
    "HN Hiring Signal": "default",
}


def get_notion_client(config: dict) -> Client:
    """Initialize Notion client from config/environment."""
    token_env = config.get("notion", {}).get("token_env_var", "NOTION_TOKEN")
    token = os.environ.get(token_env)

    if not token:
        raise ValueError(
            f"Notion token not found. Set the {token_env} environment variable.\n"
            "Create an integration at: https://www.notion.so/my-integrations"
        )

    return Client(auth=token)


def publish_leads(
    config: dict,
    scored_leads: list[ScoredLead],
    min_grade: str = "D",
) -> str:
    """
    Publish scored leads to Notion database.

    Only publishes leads at or above min_grade threshold.
    Deduplicates against existing entries by URL.

    Returns a summary string.
    """
    notion = get_notion_client(config)
    database_id = config.get("notion", {}).get("database_id", "")

    if not database_id:
        raise ValueError(
            "No Notion database_id configured. "
            "Set 'database_id' in config.yaml under 'notion'."
        )

    # Grade hierarchy for filtering
    grade_rank = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
    min_rank = grade_rank.get(min_grade, 2)

    # Filter leads by minimum grade
    qualified_leads = [
        lead for lead in scored_leads
        if grade_rank.get(lead.score.grade, 0) >= min_rank
    ]

    logger.info(
        f"Publishing {len(qualified_leads)} leads "
        f"(grade >= {min_grade}, filtered from {len(scored_leads)} total)..."
    )

    # Check existing entries to avoid duplicates
    existing_urls = _get_existing_urls(notion, database_id)

    today = datetime.now().strftime("%Y-%m-%d")
    created = 0
    skipped = 0
    errors = 0

    for lead in qualified_leads:
        r = lead.result
        sc = lead.score

        # Skip if already in database
        if r.url in existing_urls:
            skipped += 1
            continue

        # Build title
        author = lead.display_author or "Unknown"
        grade_label = GRADE_LABELS.get(sc.grade, sc.grade)
        title = f"{grade_label} — {author}"

        # Build verticals multi-select
        verticals = [
            {"name": v[:100]}
            for v in sc.matched_company_keywords[:5]
        ] if sc.matched_company_keywords else []

        # Build snippet
        snippet = lead.snippet_display
        if len(snippet) > 2000:
            snippet = snippet[:1997] + "..."

        # Build properties
        properties = {
            "Name": {
                "title": [{"text": {"content": title[:100]}}]
            },
            "Author": {
                "rich_text": [{"text": {"content": author[:100]}}]
            },
            "Lead Score": {
                "number": sc.composite_score
            },
            "Grade": {
                "select": {"name": sc.grade}
            },
            "Signal": {
                "rich_text": [{"text": {"content": r.signal_category[:100]}}]
            },
            "Platform": {
                "select": {"name": PLATFORM_MAP.get(r.platform, r.platform)}
            },
            "Title Fit": {
                "number": sc.title_fit
            },
            "Company Fit": {
                "number": sc.company_fit
            },
            "Intent Signal": {
                "number": sc.intent_signal
            },
            "Link": {
                "url": r.url
            },
            "Snippet": {
                "rich_text": [{"text": {"content": snippet}}]
            },
            "Keyword": {
                "rich_text": [{"text": {"content": r.keyword[:100]}}]
            },
            "Scraped At": {
                "date": {"start": today}
            },
            "Contacted": {
                "checkbox": False
            },
        }

        # Add verticals if we have them
        if verticals:
            properties["Verticals"] = {"multi_select": verticals}

        try:
            notion.pages.create(
                parent={"database_id": database_id},
                properties=properties,
            )
            created += 1
            logger.info(
                f"  [{created}] {grade_label} — {author} — "
                f"{sc.composite_score}/10 — {r.signal_category}"
            )
        except Exception as e:
            errors += 1
            logger.warning(f"  Failed to create lead for {r.url[:60]}: {e}")

    summary = (
        f"Published {created} new leads to Notion "
        f"({skipped} duplicates skipped, {errors} errors)"
    )
    logger.info(summary)
    return summary


def _get_existing_urls(notion: Client, database_id: str) -> set[str]:
    """Get all URLs already in the database to avoid duplicates."""
    existing = set()
    try:
        has_more = True
        start_cursor = None

        while has_more:
            kwargs = {"database_id": database_id, "page_size": 100}
            if start_cursor:
                kwargs["start_cursor"] = start_cursor

            response = notion.databases.query(**kwargs)

            for page in response.get("results", []):
                link_prop = page.get("properties", {}).get("Link", {})
                url = link_prop.get("url", "")
                if url:
                    existing.add(url)

            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")

    except Exception as e:
        logger.warning(f"Could not check existing entries: {e}")

    if existing:
        logger.info(f"Found {len(existing)} existing leads in database")

    return existing
