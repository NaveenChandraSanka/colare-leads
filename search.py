"""
Search module — finds hardtech hiring signals across LinkedIn, X, Reddit, and HN.
Uses DuckDuckGo (free, no API keys) for LinkedIn/X, and native APIs for Reddit/HN.
"""

import re
import time
import logging
import requests
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from ddgs import DDGS

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    platform: str          # "linkedin", "twitter", "reddit", "hackernews"
    signal_category: str   # "Hiring Pain", "Scaling Engineering", etc.
    keyword: str           # the keyword that found this
    source_type: str = ""  # "company_track", "people_track", "keyword_search"
    found_at: datetime = field(default_factory=datetime.now)

    @property
    def author(self) -> str:
        """Extract author from title or URL."""
        if self.platform == "linkedin":
            match = re.match(r"^(.+?)\s+on LinkedIn", self.title)
            if match:
                return match.group(1).strip()
            match = re.search(r"\|\s*(.+?)\s+posted", self.title)
            if match:
                return match.group(1).strip()
            match = re.search(r"\|\s*(.+?)$", self.title)
            if match:
                return match.group(1).strip()
        elif self.platform == "twitter":
            match = re.match(r"^(.+?)\s*\(", self.title)
            if match:
                return match.group(1).strip()
            match = re.match(r"^(.+?)\s+on X", self.title)
            if match:
                return match.group(1).strip()
        elif self.platform == "reddit":
            match = re.search(r"r/(\w+)", self.url)
            if match:
                return f"r/{match.group(1)}"
        return "Unknown"

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "platform": self.platform,
            "signal_category": self.signal_category,
            "keyword": self.keyword,
            "source_type": self.source_type,
            "author": self.author,
            "found_at": self.found_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ddgs_timelimit(days_back: int) -> str:
    """Map a days_back value to the closest DuckDuckGo timelimit string."""
    if days_back <= 1:
        return "d"   # past day
    elif days_back <= 7:
        return "w"   # past week
    else:
        return "m"   # past month (closest option for 14 days)


# ---------------------------------------------------------------------------
# DuckDuckGo-based search (LinkedIn + X)
# ---------------------------------------------------------------------------

def search_platform(
    keywords: list[str],
    signal_name: str,
    platform: str,
    max_results: int = 5,
    days_back: int = 7,
) -> list[SearchResult]:
    """Search for content on LinkedIn or X via DuckDuckGo."""
    site_filter = {
        "linkedin": "site:linkedin.com/posts",
        "twitter": "site:x.com",
    }

    timelimit = _ddgs_timelimit(days_back)

    results: list[SearchResult] = []
    seen_urls: set[str] = set()

    for keyword in keywords:
        query = f"{site_filter[platform]} {keyword}"
        logger.info(f"  Searching: {query}")

        try:
            with DDGS() as ddgs:
                search_results = list(
                    ddgs.text(query, max_results=max_results, timelimit=timelimit)
                )

            for r in search_results:
                url = r.get("href", "")

                if url in seen_urls:
                    continue
                seen_urls.add(url)

                if platform == "linkedin" and not _is_linkedin_post(url):
                    continue
                if platform == "twitter" and not _is_twitter_post(url):
                    continue

                results.append(
                    SearchResult(
                        title=r.get("title", ""),
                        url=url,
                        snippet=r.get("body", ""),
                        platform=platform,
                        signal_category=signal_name,
                        keyword=keyword,
                        source_type="keyword_search",
                    )
                )

            time.sleep(2)

        except Exception as e:
            logger.warning(f"  Search failed for '{keyword}': {e}")
            time.sleep(5)
            continue

    return results


def search_company(
    company_name: str,
    platform: str = "linkedin",
    max_results: int = 5,
    days_back: int = 14,
) -> list[SearchResult]:
    """Search for hiring-related posts from a tracked company."""
    site_filter = {
        "linkedin": "site:linkedin.com/posts",
        "twitter": "site:x.com",
    }

    query = f'{site_filter[platform]} "{company_name}" hiring OR engineers OR engineering'
    logger.info(f"  Tracking company: {query}")

    results: list[SearchResult] = []

    try:
        with DDGS() as ddgs:
            search_results = list(
                ddgs.text(query, max_results=max_results, timelimit=_ddgs_timelimit(days_back))
            )

        for r in search_results:
            url = r.get("href", "")
            results.append(
                SearchResult(
                    title=r.get("title", ""),
                    url=url,
                    snippet=r.get("body", ""),
                    platform=platform,
                    signal_category="Tracked Company",
                    keyword=company_name,
                    source_type="company_track",
                )
            )

        time.sleep(2)

    except Exception as e:
        logger.warning(f"  Company search failed for '{company_name}': {e}")

    return results


def search_person(
    person_name: str,
    platform: str = "linkedin",
    max_results: int = 5,
    days_back: int = 14,
) -> list[SearchResult]:
    """Search for recent posts by a tracked person."""
    site_filter = {
        "linkedin": "site:linkedin.com/posts",
        "twitter": "site:x.com",
    }

    query = f'{site_filter[platform]} "{person_name}"'
    logger.info(f"  Tracking person: {query}")

    results: list[SearchResult] = []

    try:
        with DDGS() as ddgs:
            search_results = list(
                ddgs.text(query, max_results=max_results, timelimit=_ddgs_timelimit(days_back))
            )

        for r in search_results:
            url = r.get("href", "")
            results.append(
                SearchResult(
                    title=r.get("title", ""),
                    url=url,
                    snippet=r.get("body", ""),
                    platform=platform,
                    signal_category="Tracked Person",
                    keyword=person_name,
                    source_type="people_track",
                )
            )

        time.sleep(2)

    except Exception as e:
        logger.warning(f"  Person search failed for '{person_name}': {e}")

    return results


# ---------------------------------------------------------------------------
# Reddit search (via DuckDuckGo — no API key needed)
# ---------------------------------------------------------------------------

def search_reddit(
    subreddits: list[str],
    keywords: list[str],
    max_results: int = 5,
    days_back: int = 7,
) -> list[SearchResult]:
    """Search Reddit for hardtech hiring discussions via DuckDuckGo."""
    timelimit = _ddgs_timelimit(days_back)
    results: list[SearchResult] = []
    seen_urls: set[str] = set()

    for subreddit in subreddits:
        for keyword in keywords:
            query = f"site:reddit.com/{subreddit} {keyword}"
            logger.info(f"  Reddit search: {query}")

            try:
                with DDGS() as ddgs:
                    search_results = list(
                        ddgs.text(query, max_results=max_results, timelimit=timelimit)
                    )

                for r in search_results:
                    url = r.get("href", "")

                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    # Filter to actual Reddit posts (not user profiles, wiki, etc.)
                    if "/comments/" not in url and "/s/" not in url:
                        continue

                    results.append(
                        SearchResult(
                            title=r.get("title", ""),
                            url=url,
                            snippet=r.get("body", ""),
                            platform="reddit",
                            signal_category="Community Discussion",
                            keyword=keyword,
                            source_type="keyword_search",
                        )
                    )

                time.sleep(2)

            except Exception as e:
                logger.warning(f"  Reddit search failed for '{keyword}' in {subreddit}: {e}")
                time.sleep(5)
                continue

    return results


# ---------------------------------------------------------------------------
# Hacker News — "Who is Hiring" threads + search
# ---------------------------------------------------------------------------

def search_hackernews(
    keywords: list[str] | None = None,
    max_results: int = 20,
    days_back: int = 14,
) -> list[SearchResult]:
    """
    Search Hacker News for hardtech hiring signals.
    Uses the free Algolia HN search API.
    """
    results: list[SearchResult] = []
    seen_urls: set[str] = set()

    # Default keywords if none provided
    if keywords is None:
        keywords = [
            "hiring mechanical engineer",
            "hiring electrical engineer",
            "hiring hardware engineer",
            "hiring robotics engineer",
            "hiring aerospace",
            "hiring embedded",
        ]

    # Calculate timestamp for N days ago
    week_ago = int((datetime.now() - timedelta(days=days_back)).timestamp())

    for keyword in keywords:
        url = (
            f"https://hn.algolia.com/api/v1/search_by_date"
            f"?query={requests.utils.quote(keyword)}"
            f"&tags=comment"
            f"&numericFilters=created_at_i>{week_ago}"
            f"&hitsPerPage={max_results}"
        )

        logger.info(f"  HN search: {keyword}")

        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                continue

            data = resp.json()
            hits = data.get("hits", [])

            for hit in hits:
                comment_text = hit.get("comment_text", "")
                story_title = hit.get("story_title", "")
                object_id = hit.get("objectID", "")
                story_id = hit.get("story_id", "")

                post_url = f"https://news.ycombinator.com/item?id={object_id}"

                if post_url in seen_urls:
                    continue
                seen_urls.add(post_url)

                # Clean HTML from comment text
                clean_text = re.sub(r"<[^>]+>", " ", comment_text)
                clean_text = re.sub(r"\s+", " ", clean_text).strip()

                results.append(
                    SearchResult(
                        title=story_title or f"HN Comment ({object_id})",
                        url=post_url,
                        snippet=clean_text[:500],
                        platform="hackernews",
                        signal_category="HN Hiring Signal",
                        keyword=keyword,
                        source_type="keyword_search",
                    )
                )

            time.sleep(1)

        except Exception as e:
            logger.warning(f"  HN search failed for '{keyword}': {e}")
            continue

    return results


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_all_searches(config: dict) -> list[SearchResult]:
    """Run all searches based on the config and return deduplicated results."""
    all_results: list[SearchResult] = []
    seen_urls: set[str] = set()

    search_config = config.get("search", {})
    max_results = search_config.get("max_results_per_query", 5)
    days_back = search_config.get("days_back", 7)
    platforms = search_config.get("platforms", {"linkedin": True, "twitter": True})
    extra_sources = search_config.get("extra_sources", {})

    def _add_results(results: list[SearchResult]):
        for r in results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                all_results.append(r)

    # ---------------------------
    # 1. Search by signal keywords
    # ---------------------------
    signals = config.get("signals", {})
    logger.info(f"Searching {len(signals)} signal categories...")

    for signal_key, signal_data in signals.items():
        signal_name = signal_data.get("label", signal_key)
        keywords = signal_data.get("keywords", [])

        if not keywords:
            continue

        logger.info(f"\n[{signal_name}] — {len(keywords)} keywords")

        for platform_name, enabled in platforms.items():
            if not enabled:
                continue

            results = search_platform(
                keywords=keywords,
                signal_name=signal_name,
                platform=platform_name,
                max_results=max_results,
                days_back=days_back,
            )
            _add_results(results)

    # ---------------------------
    # 2. Search tracked companies
    # ---------------------------
    tracked_companies = config.get("tracked_companies", [])
    if tracked_companies:
        logger.info(f"\nTracking {len(tracked_companies)} companies...")
        for company in tracked_companies:
            for platform_name, enabled in platforms.items():
                if not enabled:
                    continue
                results = search_company(
                    company_name=company,
                    platform=platform_name,
                    max_results=3,
                    days_back=days_back,
                )
                _add_results(results)

    # ---------------------------
    # 3. Search tracked people
    # ---------------------------
    tracked_people = config.get("tracked_people", [])
    if tracked_people:
        logger.info(f"\nTracking {len(tracked_people)} people...")
        for person in tracked_people:
            for platform_name, enabled in platforms.items():
                if not enabled:
                    continue
                results = search_person(
                    person_name=person,
                    platform=platform_name,
                    max_results=3,
                    days_back=days_back,
                )
                _add_results(results)

    # ---------------------------
    # 4. Reddit
    # ---------------------------
    if extra_sources.get("reddit"):
        reddit_config = config.get("reddit", {})
        subreddits = reddit_config.get("subreddits", [])
        reddit_keywords = reddit_config.get("keywords", [])

        if subreddits and reddit_keywords:
            logger.info(f"\nSearching Reddit ({len(subreddits)} subreddits)...")
            results = search_reddit(
                subreddits=subreddits,
                keywords=reddit_keywords,
                max_results=3,
                days_back=days_back,
            )
            _add_results(results)

    # ---------------------------
    # 5. Hacker News
    # ---------------------------
    if extra_sources.get("hackernews"):
        logger.info("\nSearching Hacker News...")
        hn_keywords = [
            "hiring mechanical engineer",
            "hiring electrical engineer",
            "hiring hardware engineer",
            "hiring robotics",
            "hiring aerospace",
            "hiring embedded systems",
            "technical assessment hardware",
        ]
        results = search_hackernews(keywords=hn_keywords, max_results=10, days_back=days_back)
        _add_results(results)

    logger.info(f"\nTotal results found: {len(all_results)}")
    return all_results


# ---------------------------------------------------------------------------
# URL validators
# ---------------------------------------------------------------------------

def _is_linkedin_post(url: str) -> bool:
    url_lower = url.lower()
    return any(p in url_lower for p in ["/posts/", "/pulse/", "/feed/update/", "/activity/"])


def _is_twitter_post(url: str) -> bool:
    return "/status/" in url.lower()
