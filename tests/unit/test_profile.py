"""Durable player coaching profile tests."""

from __future__ import annotations

from pathlib import Path

from tests.fixtures.mock_engine import ScriptedLossEngine
from tests.fixtures.sample_data import SAMPLE_PGN_BLACK, SAMPLE_PGN_WHITE

from check_yourself.coaching.profile_store import load_profile, profile_path
from check_yourself.config import AnalysisSettings
from check_yourself.models import AnalysisReport, CoachingReport, GameCoaching
from check_yourself.pipeline import analyze_games_offline, recoach_from_report
from check_yourself.providers.chess_com import parse_pgn_metadata


def _metas():
    out = []
    for pgn, end in ((SAMPLE_PGN_WHITE, 1), (SAMPLE_PGN_BLACK, 2)):
        meta = parse_pgn_metadata(pgn, username="TestPlayer", end_time=end)
        assert meta is not None
        out.append(meta)
    return out


def test_recoach_from_report_updates_profile_without_llm(tmp_path: Path) -> None:
    settings = AnalysisSettings(depth=2, default_players_dir=tmp_path / "players")
    engine = ScriptedLossEngine(start_cp=250, drop_per_player_move=200)
    report, run_dir = analyze_games_offline(
        "TestPlayer",
        _metas(),
        engine,
        settings=settings,
        output_dir=tmp_path / "reports",
        persist_profile=True,
    )
    assert report.habits is not None
    analysis_json = run_dir / "analysis.json"
    assert analysis_json.is_file()

    report2, path, profile_out = recoach_from_report(
        run_dir,
        settings=settings,
        use_llm=False,
    )
    assert path == analysis_json
    assert profile_out is not None
    assert profile_out.is_file()
    profile = load_profile(profile_out)
    assert profile is not None
    assert profile.username == "TestPlayer"
    assert len(profile.sessions) >= 1
    assert report2.habits is not None


def test_recoach_with_stub_llm_reuses_prior_profile(tmp_path: Path) -> None:
    settings = AnalysisSettings(depth=2, default_players_dir=tmp_path / "players")
    engine = ScriptedLossEngine(start_cp=250, drop_per_player_move=200)

    class StubCoach:
        def __init__(self) -> None:
            self.saw_prior = False

        def coach(
            self,
            report: AnalysisReport,
            *,
            prior_profile: object | None = None,
        ) -> CoachingReport:
            self.saw_prior = prior_profile is not None and getattr(
                prior_profile, "sessions", []
            ) != []
            return CoachingReport(
                model="stub-model",
                instruction_pack="v1",
                overall_summary="Focus on conversion this session.",
                themes=["conversion"],
                practice_suggestions=["Calculate forcing moves"],
                games=[
                    GameCoaching(
                        game_id=g.metadata.game_id,
                        summary="Review the critical ply.",
                        themes=["tactics"],
                        critical_notes=[],
                        practice_suggestions=[],
                    )
                    for g in report.games
                ],
                generated_at=report.settings.analyzed_at,
            )

    # First session creates profile
    report, run_dir = analyze_games_offline(
        "TestPlayer",
        _metas(),
        engine,
        settings=settings,
        output_dir=tmp_path / "reports",
        coach=True,
        coaching_provider=StubCoach(),
        persist_profile=True,
    )
    assert report.coaching is not None
    prof_path = profile_path(settings.default_players_dir, "TestPlayer", "chess.com")
    assert prof_path.is_file()

    stub = StubCoach()
    report2, _, profile_out = recoach_from_report(
        run_dir,
        settings=settings,
        coaching_provider=stub,
        use_llm=True,
    )
    assert stub.saw_prior is True
    assert report2.coaching is not None
    assert report2.coaching.overall_summary.startswith("Focus on conversion")
    profile = load_profile(profile_out) if profile_out else None
    assert profile is not None
    assert "conversion" in " ".join(profile.recurring_themes).lower() or profile.coach_narrative
    assert len(profile.sessions) >= 1
