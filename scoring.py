"""
Lead Scoring Engine — scores each discovered post/person on 3 axes:

  1. Title Fit (0-10)   — Is this person a decision-maker for hiring tools?
  2. Company Fit (0-10)  — Is the company in a hardtech vertical?
  3. Intent Signal (0-10) — Does the post indicate active hiring pain or scale?

Combined lead score = (title * 0.25) + (company * 0.25) + (intent * 0.50)
Intent is weighted 2x because timing matters most for outbound.
"""

import re
import logging
from dataclasses import dataclass, field
from search import SearchResult

logger = logging.getLogger(__name__)


@dataclass
class LeadScore:
    title_fit: float = 0.0      # 0-10
    company_fit: float = 0.0    # 0-10
    intent_signal: float = 0.0  # 0-10
    signal_weight: float = 1.0  # from config signal category weight
    matched_title_keywords: list[str] = field(default_factory=list)
    matched_company_keywords: list[str] = field(default_factory=list)
    matched_intent_keywords: list[str] = field(default_factory=list)

    @property
    def composite_score(self) -> float:
        """
        Weighted composite: intent is 50%, title and company 25% each.
        Signal category weight acts as a multiplier (1-3x).
        """
        raw = (
            (self.title_fit * 0.25)
            + (self.company_fit * 0.25)
            + (self.intent_signal * 0.50)
        )
        # Apply signal weight as a boost (1x-3x), then cap at 10
        return min(round(raw * self.signal_weight, 2), 10.0)

    @property
    def grade(self) -> str:
        """Letter grade for quick scanning."""
        score = self.composite_score
        if score >= 8.0:
            return "A"
        elif score >= 6.0:
            return "B"
        elif score >= 4.0:
            return "C"
        elif score >= 2.0:
            return "D"
        return "F"

    @property
    def grade_emoji(self) -> str:
        grades = {
            "A": "🔥 HOT LEAD",
            "B": "🟢 STRONG",
            "C": "🟡 WARM",
            "D": "⚪ WEAK",
            "F": "❌ LOW",
        }
        return grades.get(self.grade, "—")

    def summary(self) -> str:
        return (
            f"Score: {self.composite_score}/10 ({self.grade_emoji}) | "
            f"Title: {self.title_fit} · Company: {self.company_fit} · "
            f"Intent: {self.intent_signal}"
        )


@dataclass
class ScoredLead:
    """A search result enriched with lead scoring."""
    result: SearchResult
    score: LeadScore
    engagement_reactions: int = 0
    engagement_comments: int = 0
    engagement_reposts: int = 0
    author_from_page: str = ""
    full_text: str = ""
    date_published: str = ""

    @property
    def display_author(self) -> str:
        if self.author_from_page:
            return self.author_from_page
        author = self.result.author
        return author if author != "Unknown" else ""

    @property
    def snippet_display(self) -> str:
        if self.full_text:
            return self.full_text[:400]
        return self.result.snippet[:400]

    @property
    def total_engagement(self) -> int:
        return self.engagement_reactions + (self.engagement_comments * 3) + (self.engagement_reposts * 2)

    @property
    def platform_label(self) -> str:
        labels = {
            "linkedin": "🔗 LinkedIn",
            "twitter": "𝕏 Twitter/X",
            "reddit": "💬 Reddit",
            "hackernews": "🟠 Hacker News",
        }
        return labels.get(self.result.platform, self.result.platform)


def score_title_fit(text: str, config: dict) -> tuple[float, list[str]]:
    """
    Score how well the author's title matches a hiring decision-maker.
    Returns (score, matched_keywords).
    """
    text_lower = text.lower()
    scoring_config = config.get("scoring", {})
    title_keywords = scoring_config.get("title_keywords", {})

    matched = []
    score = 0.0

    # High fit: 8-10 points
    for kw in title_keywords.get("high_fit", []):
        if kw.lower() in text_lower:
            score = max(score, 9.0)
            matched.append(kw)

    # Medium fit: 4-6 points
    for kw in title_keywords.get("medium_fit", []):
        if kw.lower() in text_lower:
            score = max(score, 5.0)
            matched.append(kw)

    # Low fit: 1-3 points
    for kw in title_keywords.get("low_fit", []):
        if kw.lower() in text_lower:
            score = max(score, 2.0)
            matched.append(kw)

    return score, matched


def score_company_fit(text: str, config: dict) -> tuple[float, list[str]]:
    """
    Score whether the post references a hardtech company/vertical.
    Returns (score, matched_keywords).
    """
    text_lower = text.lower()
    scoring_config = config.get("scoring", {})
    verticals = scoring_config.get("company_verticals", [])

    matched = [v for v in verticals if v.lower() in text_lower]

    # Also check tracked companies
    tracked = config.get("tracked_companies", [])
    for company in tracked:
        if company.lower() in text_lower:
            matched.append(company)

    if not matched:
        return 0.0, []

    # More matches = higher confidence it's a real hardtech context
    # 1 match = 5, 2 = 7, 3+ = 9
    if len(matched) >= 3:
        return 9.0, matched
    elif len(matched) >= 2:
        return 7.0, matched
    else:
        return 5.0, matched


def score_intent_signal(text: str, config: dict) -> tuple[float, list[str]]:
    """
    Score the buying intent — is this person actively struggling with hiring?
    Returns (score, matched_keywords).
    """
    text_lower = text.lower()
    scoring_config = config.get("scoring", {})
    intent_keywords = scoring_config.get("intent_keywords", [])

    matched = [kw for kw in intent_keywords if kw.lower() in text_lower]

    if not matched:
        return 0.0, []

    # Strong intent signals get extra weight
    strong_signals = [
        "can't find", "struggling to hire", "talent shortage",
        "mis-hire", "time to hire", "days to fill",
        "technical assessment", "interview process",
    ]
    strong_matches = [s for s in strong_signals if s in text_lower]

    base_score = min(len(matched) * 2.0, 7.0)

    if strong_matches:
        base_score = min(base_score + 3.0, 10.0)

    return base_score, matched


def score_lead(result: SearchResult, config: dict) -> LeadScore:
    """
    Score a single search result across all 3 axes.
    """
    # Combine all text for analysis
    full_text = f"{result.title} {result.snippet}".strip()

    # Get signal weight from config
    signals = config.get("signals", {})
    signal_weight = 1.0
    for signal_data in signals.values():
        if signal_data.get("label") == result.signal_category:
            signal_weight = signal_data.get("weight", 1.0)
            break

    # Score each axis
    title_score, title_matches = score_title_fit(full_text, config)
    company_score, company_matches = score_company_fit(full_text, config)
    intent_score, intent_matches = score_intent_signal(full_text, config)

    # Tracked companies/people get automatic boosts
    if result.source_type == "company_track":
        company_score = max(company_score, 8.0)
        intent_score = max(intent_score, 4.0)

    if result.source_type == "people_track":
        title_score = max(title_score, 6.0)

    return LeadScore(
        title_fit=title_score,
        company_fit=company_score,
        intent_signal=intent_score,
        signal_weight=signal_weight,
        matched_title_keywords=title_matches,
        matched_company_keywords=company_matches,
        matched_intent_keywords=intent_matches,
    )


def score_all_leads(
    results: list[SearchResult],
    config: dict,
) -> list[ScoredLead]:
    """
    Score all search results and return sorted by composite score.
    """
    scored: list[ScoredLead] = []

    for result in results:
        lead_score = score_lead(result, config)
        scored.append(ScoredLead(result=result, score=lead_score))

    # Sort by composite score descending
    scored.sort(key=lambda s: s.score.composite_score, reverse=True)

    # Log distribution
    grades = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for s in scored:
        grades[s.score.grade] = grades.get(s.score.grade, 0) + 1

    logger.info(
        f"Lead scores: {len(scored)} total — "
        f"🔥 {grades['A']} A · 🟢 {grades['B']} B · 🟡 {grades['C']} C · "
        f"⚪ {grades['D']} D · ❌ {grades['F']} F"
    )

    return scored


def leads_to_markdown(scored_leads: list[ScoredLead], config: dict) -> str:
    """Convert scored leads to a Markdown report."""
    lines = []
    from datetime import datetime

    lines.append(f"# Colare Lead Scout — {datetime.now().strftime('%A, %B %d, %Y')}")
    lines.append("")
    lines.append(f"**{len(scored_leads)} leads discovered** across LinkedIn, X, Reddit, and HN")
    lines.append("")

    # Grade distribution
    grades = {}
    for s in scored_leads:
        g = s.score.grade
        grades[g] = grades.get(g, 0) + 1

    lines.append(
        f"| Grade | Count |\n|-------|-------|\n"
        + "\n".join(f"| {g} | {grades.get(g, 0)} |" for g in ["A", "B", "C", "D", "F"])
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # Hot leads first (A and B grade)
    hot_leads = [s for s in scored_leads if s.score.grade in ("A", "B")]
    if hot_leads:
        lines.append("## 🔥 Hot Leads (Grade A & B)")
        lines.append("")
        lines.append("*These are your highest-priority outreach targets.*")
        lines.append("")

        for i, lead in enumerate(hot_leads, 1):
            r = lead.result
            sc = lead.score

            lines.append(f"### {i}. {sc.grade_emoji} — {lead.display_author or 'Unknown'}")
            lines.append(f"**Score:** {sc.composite_score}/10 | "
                         f"Title: {sc.title_fit} · Company: {sc.company_fit} · Intent: {sc.intent_signal}")
            lines.append(f"**Signal:** {r.signal_category} | **Source:** {lead.platform_label}")
            lines.append(f"**Keyword:** `{r.keyword}`")

            if sc.matched_company_keywords:
                lines.append(f"**Verticals:** {', '.join(sc.matched_company_keywords[:5])}")
            if sc.matched_intent_keywords:
                lines.append(f"**Intent signals:** {', '.join(sc.matched_intent_keywords[:5])}")

            lines.append("")

            snippet = lead.snippet_display
            if snippet:
                if len(snippet) > 300:
                    snippet = snippet[:300].rsplit(" ", 1)[0] + "..."
                lines.append(f"> {snippet}")
                lines.append("")

            lines.append(f"[→ View post]({r.url})")
            lines.append("")
            lines.append("---")
            lines.append("")

    # Warm leads (C grade)
    warm_leads = [s for s in scored_leads if s.score.grade == "C"]
    if warm_leads:
        lines.append("## 🟡 Warm Leads (Grade C)")
        lines.append("")

        for i, lead in enumerate(warm_leads, 1):
            r = lead.result
            sc = lead.score

            lines.append(
                f"**{i}. {lead.display_author or 'Unknown'}** — "
                f"{sc.composite_score}/10 | {r.signal_category} | "
                f"[View]({r.url})"
            )

        lines.append("")
        lines.append("---")
        lines.append("")

    # Summary by signal category
    lines.append("## 📊 Breakdown by Signal")
    lines.append("")

    by_signal: dict[str, list[ScoredLead]] = {}
    for lead in scored_leads:
        cat = lead.result.signal_category
        if cat not in by_signal:
            by_signal[cat] = []
        by_signal[cat].append(lead)

    for cat, leads in sorted(by_signal.items(), key=lambda x: -len(x[1])):
        avg_score = sum(l.score.composite_score for l in leads) / len(leads) if leads else 0
        lines.append(f"- **{cat}**: {len(leads)} leads (avg score: {avg_score:.1f})")

    lines.append("")

    # Platform breakdown
    lines.append("## 🌐 Breakdown by Platform")
    lines.append("")

    by_platform: dict[str, int] = {}
    for lead in scored_leads:
        p = lead.result.platform
        by_platform[p] = by_platform.get(p, 0) + 1

    for platform, count in sorted(by_platform.items(), key=lambda x: -x[1]):
        lines.append(f"- **{platform.title()}**: {count} leads")

    lines.append("")

    return "\n".join(lines)
