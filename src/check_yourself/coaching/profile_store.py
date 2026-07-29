"""Durable per-player coaching profile store."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from check_yourself.models import (
    AnalysisReport,
    CoachingReport,
    PersistentHabitNote,
    PlayerCoachingProfile,
    ProfileSessionRef,
)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def profile_slug(username: str, platform: str) -> str:
    user = _SAFE_NAME.sub("_", username.strip().lower()).strip("._-") or "player"
    plat = _SAFE_NAME.sub("_", platform.strip().lower()).strip("._-") or "chess.com"
    return f"{user}__{plat}"


def profile_path(players_dir: Path, username: str, platform: str) -> Path:
    return Path(players_dir) / profile_slug(username, platform) / "profile.json"


def load_profile(path: Path) -> PlayerCoachingProfile | None:
    if not path.is_file():
        return None
    return PlayerCoachingProfile.model_validate_json(path.read_text(encoding="utf-8"))


def save_profile(profile: PlayerCoachingProfile, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    return path


def empty_profile(username: str, platform: str) -> PlayerCoachingProfile:
    now = datetime.now(UTC)
    return PlayerCoachingProfile(
        username=username,
        platform=platform,
        created_at=now,
        updated_at=now,
    )


def profile_brief_for_coaching(profile: PlayerCoachingProfile) -> dict[str, object]:
    """Compact prior-memory payload for LLM delta coaching."""
    return {
        "username": profile.username,
        "platform": profile.platform,
        "sessions_recorded": len(profile.sessions),
        "coach_narrative": profile.coach_narrative,
        "recurring_themes": profile.recurring_themes[:8],
        "practice_focus": profile.practice_focus[:8],
        "active_habits": [
            {
                "id": h.id,
                "title": h.title,
                "severity": h.severity,
                "summary": h.summary,
                "practice_hint": h.practice_hint,
                "times_seen": h.times_seen,
                "status": h.status,
            }
            for h in profile.active_habits
            if h.status == "active"
        ][:8],
        "recent_session_summaries": profile.recent_session_summaries[-3:],
    }


def merge_profile(
    existing: PlayerCoachingProfile | None,
    report: AnalysisReport,
    *,
    report_path: str | Path,
    coaching: CoachingReport | None = None,
) -> PlayerCoachingProfile:
    """Merge a new analysis/coaching session into the durable player profile."""
    now = datetime.now(UTC)
    username = report.settings.username
    platform = report.settings.platform
    profile = existing or empty_profile(username, platform)
    profile.username = username
    profile.platform = platform
    profile.updated_at = now

    coaching = coaching if coaching is not None else report.coaching
    session = ProfileSessionRef(
        report_path=str(report_path),
        analyzed_at=report.settings.analyzed_at,
        games_analyzed=report.overall.games_analyzed,
        platform=platform,
        coaching_model=(coaching.model if coaching else report.settings.coaching_model),
    )
    # Avoid duplicate session entries for the same report path.
    profile.sessions = [s for s in profile.sessions if s.report_path != session.report_path]
    profile.sessions.append(session)
    profile.sessions = profile.sessions[-20:]

    # Merge habit findings
    seen_ids: set[str] = set()
    by_id = {h.id: h for h in profile.active_habits}
    if report.habits is not None:
        for finding in report.habits.findings:
            seen_ids.add(finding.id)
            prior = by_id.get(finding.id)
            if prior is None:
                by_id[finding.id] = PersistentHabitNote(
                    id=finding.id,
                    title=finding.title,
                    severity=finding.severity.value,
                    summary=finding.summary,
                    practice_hint=finding.practice_hint,
                    first_seen_at=now,
                    last_seen_at=now,
                    times_seen=1,
                    status="active",
                )
            else:
                prior.title = finding.title
                prior.severity = finding.severity.value
                prior.summary = finding.summary
                prior.practice_hint = finding.practice_hint
                prior.last_seen_at = now
                prior.times_seen += 1
                prior.status = "active"

        # Habits not seen this session but previously active → improved (still kept)
        for hid, note in by_id.items():
            if hid not in seen_ids and note.status == "active":
                note.status = "improved"

    profile.active_habits = sorted(
        by_id.values(),
        key=lambda h: (0 if h.status == "active" else 1, -h.times_seen, h.id),
    )[:12]

    if coaching is not None:
        if coaching.overall_summary.strip():
            profile.coach_narrative = coaching.overall_summary.strip()
            profile.recent_session_summaries.append(coaching.overall_summary.strip())
            profile.recent_session_summaries = profile.recent_session_summaries[-5:]
        profile.recurring_themes = _merge_unique(
            profile.recurring_themes,
            coaching.themes,
            limit=10,
        )
        profile.practice_focus = _merge_unique(
            profile.practice_focus,
            coaching.practice_suggestions,
            limit=10,
        )

    return profile


def _merge_unique(prior: list[str], new: list[str], *, limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in [*new, *prior]:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
        if len(out) >= limit:
            break
    return out
