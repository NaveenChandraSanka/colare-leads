#!/usr/bin/env python3
"""
Colare Lead Scout — Weekly hardtech hiring signal discovery.

Searches LinkedIn, X, Reddit, and Hacker News for posts that indicate
companies are hiring engineers, struggling with assessments, or scaling
hardware teams. Scores each post as a potential enterprise lead for Colare
and publishes results to a Notion database.

Usage:
    python main.py                  # Run once (search + score + publish)
    python main.py --dry-run        # Search + score, print to terminal
    python main.py --markdown       # Save as local markdown report
    python main.py --schedule       # Run weekly at configured time
    python main.py --min-grade B    # Only publish grade B+ leads
"""

import os
import sys
import yaml
import logging
import argparse
from datetime import datetime
from pathlib import Path

from search import run_all_searches
from scoring import score_all_leads, leads_to_markdown


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)

    with open(path) as f:
        return yaml.safe_load(f)


def run_scout(
    config: dict,
    dry_run: bool = False,
    save_markdown: bool = False,
    min_grade: str = "D",
) -> str | None:
    """
    Main pipeline: search -> score -> publish.

    Returns Notion summary if published, None otherwise.
    """
    niche_name = config.get("niche", {}).get("name", "Unknown")
    logger.info(f"{'='*60}")
    logger.info(f"Colare Lead Scout — {niche_name}")
    logger.info(f"{'='*60}")

    # Step 1: Search all sources
    logger.info("\n📡 STEP 1: Searching for hardtech hiring signals...")
    results = run_all_searches(config)

    if not results:
        logger.warning("No results found. Try adjusting keywords in config.yaml")
        return None

    logger.info(f"\n✅ Found {len(results)} posts across all sources")

    # Step 2: Score leads
    logger.info("\n📊 STEP 2: Scoring leads...")
    scored_leads = score_all_leads(results, config)

    # Step 3: Generate report
    logger.info("\n📝 STEP 3: Generating report...")
    markdown = leads_to_markdown(scored_leads, config)

    # Step 4: Output
    if dry_run:
        print("\n" + "=" * 60)
        print(markdown)
        print("=" * 60)
        return None

    if save_markdown:
        date_str = datetime.now().strftime("%Y-%m-%d")
        output_dir = Path("reports")
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / f"leads-{date_str}.md"
        output_path.write_text(markdown)
        logger.info(f"📄 Saved report to: {output_path}")

    # Step 5: Publish to Notion
    notion_config = config.get("notion", {})
    db_env = notion_config.get("database_id_env_var", "NOTION_DATABASE_ID")
    database_id = os.environ.get(db_env, "")

    if not database_id:
        logger.warning(
            "No Notion database_id configured. Skipping Notion publish.\n"
            "Set 'database_id' in config.yaml to enable."
        )
        if not save_markdown:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_dir = Path("reports")
            output_dir.mkdir(exist_ok=True)
            output_path = output_dir / f"leads-{date_str}.md"
            output_path.write_text(markdown)
            logger.info(f"📄 Saved fallback report to: {output_path}")
        return None

    try:
        from notion_publisher import publish_leads
        summary = publish_leads(config, scored_leads, min_grade=min_grade)
        logger.info(f"\n🚀 {summary}")
        return summary
    except Exception as e:
        logger.error(f"Failed to publish to Notion: {e}")
        if not save_markdown:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_dir = Path("reports")
            output_dir.mkdir(exist_ok=True)
            output_path = output_dir / f"leads-{date_str}.md"
            output_path.write_text(markdown)
            logger.info(f"📄 Saved fallback report to: {output_path}")
        return None


def run_scheduled(config: dict, min_grade: str = "D"):
    """Run the scout on a weekly schedule."""
    import schedule
    import time

    sched_config = config.get("schedule", {})
    run_time = sched_config.get("run_time", "08:00")
    run_day = sched_config.get("run_day", "monday").lower()

    logger.info(f"Scheduling weekly scout at {run_time} every {run_day.title()}")

    day_map = {
        "monday": schedule.every().monday,
        "tuesday": schedule.every().tuesday,
        "wednesday": schedule.every().wednesday,
        "thursday": schedule.every().thursday,
        "friday": schedule.every().friday,
        "saturday": schedule.every().saturday,
        "sunday": schedule.every().sunday,
    }
    day_schedule = day_map.get(run_day, schedule.every().monday)
    day_schedule.at(run_time).do(
        run_scout, config=config, save_markdown=True, min_grade=min_grade
    )

    # Run immediately on first start
    logger.info("Running initial scout now...")
    run_scout(config, save_markdown=True, min_grade=min_grade)

    logger.info(
        f"Scheduler active. Next run: {run_day.title()} at {run_time}. "
        f"Press Ctrl+C to stop."
    )
    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(
        description="Colare Lead Scout — Weekly hardtech hiring signal discovery"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search + score, print results to terminal without publishing",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Save report as a local markdown file",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run on a weekly schedule (configure in config.yaml)",
    )
    parser.add_argument(
        "--min-grade",
        default="D",
        choices=["A", "B", "C", "D", "F"],
        help="Minimum lead grade to publish to Notion (default: D)",
    )

    args = parser.parse_args()
    config = load_config(args.config)

    if args.schedule:
        run_scheduled(config, min_grade=args.min_grade)
    else:
        run_scout(
            config,
            dry_run=args.dry_run,
            save_markdown=args.markdown or args.dry_run,
            min_grade=args.min_grade,
        )


if __name__ == "__main__":
    main()
