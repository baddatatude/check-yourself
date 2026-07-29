"""OpenAI coaching provider tests (mocked HTTP)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from tests.fixtures.mock_engine import ScriptedLossEngine
from tests.fixtures.sample_data import SAMPLE_PGN_BLACK, SAMPLE_PGN_WHITE

from check_yourself.analysis.game_analyzer import GameAnalyzer
from check_yourself.config import AnalysisSettings
from check_yourself.models import (
    AnalysisReport,
    AnalysisRunSettings,
    CoachingReport,
    CriticalCoachingNote,
    GameCoaching,
    OverallStats,
)
from check_yourself.pipeline import analyze_games_offline
from check_yourself.providers.chess_com import parse_pgn_metadata
from check_yourself.providers.coaching import (
    CoachingError,
    OpenAICoachingProvider,
    build_game_coaching_payload,
    probe_openai_key,
)


def _metas():
    out = []
    for pgn, end in ((SAMPLE_PGN_WHITE, 1), (SAMPLE_PGN_BLACK, 2)):
        meta = parse_pgn_metadata(pgn, username="TestPlayer", end_time=end)
        assert meta is not None
        out.append(meta)
    return out


def _fake_coaching_json(game_ids: list[str]) -> str:
    return json.dumps(
        {
            "overall_summary": "Focus on converting advantages and avoiding one-move blunders.",
            "themes": ["conversion", "hanging pieces"],
            "practice_suggestions": ["Solve 10 tactics daily", "Play slower in winning positions"],
            "games": [
                {
                    "game_id": gid,
                    "summary": f"Review turning points in {gid}.",
                    "themes": ["tactics"],
                    "critical_notes": [{"ply": 10, "note": "Prefer the engine continuation."}],
                    "practice_suggestions": ["Recalculate checks and captures"],
                }
                for gid in game_ids
            ],
        }
    )


def test_build_game_payload_is_compact() -> None:
    settings = AnalysisSettings(depth=2)
    engine = ScriptedLossEngine()
    meta = parse_pgn_metadata(SAMPLE_PGN_WHITE, username="TestPlayer", end_time=1)
    assert meta is not None
    result = GameAnalyzer(engine, settings).analyze(meta)
    payload = build_game_coaching_payload(result, max_critical=3, max_error_moves=5)
    assert payload["game_id"] == meta.game_id
    assert "pgn" in payload
    assert "critical_positions" in payload
    assert "top_error_moves" in payload
    assert "moves" not in payload


def test_openai_provider_parses_structured_response() -> None:
    from datetime import UTC, datetime

    settings = AnalysisSettings(depth=2)
    engine = ScriptedLossEngine()
    metas = _metas()
    analyzed = [GameAnalyzer(engine, settings).analyze(m) for m in metas]
    report = AnalysisReport(
        settings=AnalysisRunSettings(
            username="TestPlayer",
            games_requested=2,
            games_found=2,
            stockfish_path="mock",
            depth=2,
            multipv=1,
            pv_moves=6,
            inaccuracy_threshold=50,
            mistake_threshold=100,
            blunder_threshold=200,
            max_critical_positions=5,
            analyzed_at=datetime.now(UTC),
        ),
        overall=OverallStats(games_analyzed=2),
        games=analyzed,
    )

    game_ids = [g.metadata.game_id for g in analyzed]

    def handler(request: httpx.Request) -> httpx.Response:
        assert "chat/completions" in str(request.url)
        assert request.headers.get("Authorization", "").startswith("Bearer sk-test")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": _fake_coaching_json(game_ids)}}]},
        )

    with OpenAICoachingProvider(
        "sk-test",
        model="gpt-4.1-mini",
        transport=httpx.MockTransport(handler),
        chunk_size=5,
    ) as provider:
        coaching = provider.coach(report)

    assert coaching.overall_summary.startswith("Focus on converting")
    assert len(coaching.games) == 2
    assert coaching.games[0].critical_notes[0].ply == 10


def test_openai_provider_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    settings = AnalysisSettings(depth=2)
    engine = ScriptedLossEngine()
    meta = _metas()[0]
    analyzed = GameAnalyzer(engine, settings).analyze(meta)
    from datetime import UTC, datetime

    report = AnalysisReport(
        settings=AnalysisRunSettings(
            username="TestPlayer",
            games_requested=1,
            games_found=1,
            stockfish_path="mock",
            depth=2,
            multipv=1,
            pv_moves=6,
            inaccuracy_threshold=50,
            mistake_threshold=100,
            blunder_threshold=200,
            max_critical_positions=5,
            analyzed_at=datetime.now(UTC),
        ),
        overall=OverallStats(games_analyzed=1),
        games=[analyzed],
    )
    with (
        OpenAICoachingProvider("sk-bad", transport=httpx.MockTransport(handler)) as provider,
        pytest.raises(CoachingError, match="authentication"),
    ):
        provider.coach(report)


def test_offline_report_with_injected_coach(tmp_path: Path) -> None:
    metas = _metas()
    settings = AnalysisSettings(depth=2, default_players_dir=tmp_path / "players")
    engine = ScriptedLossEngine()

    class StubCoach:
        def coach(
            self,
            report: AnalysisReport,
            *,
            prior_profile: object | None = None,
        ) -> CoachingReport:
            return CoachingReport(
                model="stub-model",
                instruction_pack="v1",
                overall_summary="Work on converting edges.",
                themes=["conversion"],
                practice_suggestions=["Calculate forcing moves first"],
                games=[
                    GameCoaching(
                        game_id=g.metadata.game_id,
                        summary="Watch the critical ply.",
                        themes=["tactics"],
                        critical_notes=[
                            CriticalCoachingNote(ply=8, note="Prefer the Stockfish move.")
                        ],
                        practice_suggestions=["Slow down when ahead"],
                    )
                    for g in report.games
                ],
                generated_at=report.settings.analyzed_at,
            )

    report, run_dir = analyze_games_offline(
        "TestPlayer",
        metas,
        engine,
        settings=settings,
        output_dir=tmp_path,
        coach=True,
        coaching_provider=StubCoach(),
    )

    assert report.coaching is not None
    assert report.settings.coaching_enabled is True
    assert report.settings.coaching_model == "stub-model"
    assert len(report.coaching.games) == 2

    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "AI coaching" in html
    assert "Work on converting edges." in html
    assert "Coaching notes" in html
    dumped = (run_dir / "analysis.json").read_text(encoding="utf-8")
    assert "sk-" not in dumped
    assert "coaching" in dumped


def test_coach_soft_fails_without_breaking_report(tmp_path: Path) -> None:
    metas = _metas()
    settings = AnalysisSettings(depth=2, default_players_dir=tmp_path / "players")
    engine = ScriptedLossEngine()

    class BoomCoach:
        def coach(
            self,
            report: AnalysisReport,
            *,
            prior_profile: object | None = None,
        ) -> CoachingReport:
            raise CoachingError("boom")

    report, run_dir = analyze_games_offline(
        "TestPlayer",
        metas,
        engine,
        settings=settings,
        output_dir=tmp_path,
        coach=True,
        coaching_provider=BoomCoach(),
    )
    assert report.coaching is None
    assert report.settings.coaching_enabled is False
    assert any("Coaching skipped" in w for w in report.warnings)
    assert (run_dir / "report.html").is_file()


def test_probe_openai_key() -> None:
    ok, detail = probe_openai_key("sk-abc")
    assert ok
    assert "configured" in detail.lower()
    ok2, _ = probe_openai_key(None)
    assert not ok2
