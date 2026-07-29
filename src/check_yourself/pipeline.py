"""Orchestration pipeline for analyze runs."""

from __future__ import annotations

import logging
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from check_yourself.analysis.aggregate import aggregate_stats
from check_yourself.analysis.game_analyzer import GameAnalyzer
from check_yourself.analysis.habit_analyzer import analyze_habits
from check_yourself.analysis.tactics_analyzer import analyze_piece_and_tactics
from check_yourself.coaching.profile_store import (
    load_profile,
    merge_profile,
    profile_path,
    save_profile,
)
from check_yourself.config import AnalysisSettings, TimeControlFilter
from check_yourself.engine.stockfish import EngineAdapter, EngineError, StockfishEngine
from check_yourself.models import (
    AnalysisReport,
    AnalysisRunSettings,
    GameAnalysisResult,
    GameMetadata,
    PlayerCoachingProfile,
)
from check_yourself.providers.base import GameSource, create_game_source, normalize_platform
from check_yourself.providers.chess_com import ChessComClient
from check_yourself.providers.coaching import (
    CoachingError,
    CoachingProvider,
    OpenAICoachingProvider,
)
from check_yourself.reports.html import write_html_report
from check_yourself.reports.json_report import (
    load_analysis_json,
    write_analysis_json,
    write_game_json,
)

logger = logging.getLogger(__name__)


def _analyze_games_sequential(
    metadata_list: list[GameMetadata],
    engine: EngineAdapter,
    settings: AnalysisSettings,
    games_dir: Path,
) -> list[GameAnalysisResult]:
    analyzer = GameAnalyzer(engine, settings)
    analyzed: list[GameAnalysisResult] = []
    for meta in metadata_list:
        logger.info("Analyzing game %s (%s)", meta.game_id, meta.user_color)
        result = analyzer.analyze(meta)
        analyzed.append(result)
        write_game_json(result, games_dir / f"{meta.game_id}.json")
    return analyzed


def _open_engine_pool(settings: AnalysisSettings, workers: int) -> list[StockfishEngine]:
    """Start ``workers`` Stockfish processes; close any opened on failure."""
    engines: list[StockfishEngine] = []
    try:
        for _ in range(workers):
            eng = StockfishEngine.from_settings(settings)
            eng.open()
            engines.append(eng)
    except EngineError:
        for eng in engines:
            eng.close()
        raise
    return engines


def _analyze_games_parallel(
    metadata_list: list[GameMetadata],
    settings: AnalysisSettings,
    workers: int,
    games_dir: Path,
    *,
    engines: list[EngineAdapter] | None = None,
) -> list[GameAnalysisResult]:
    """Analyze games with one engine per worker; preserve input order.

    When ``engines`` is omitted, starts ``workers`` Stockfish processes.
    """
    owns_engines = engines is None
    pool_engines: list[EngineAdapter] = (
        list(engines) if engines is not None else list(_open_engine_pool(settings, workers))
    )
    if len(pool_engines) < 1:
        raise EngineError("Parallel analysis requires at least one engine")

    worker_count = min(workers, len(pool_engines))
    engine_pool: queue.Queue[EngineAdapter] = queue.Queue()
    for eng in pool_engines:
        engine_pool.put(eng)

    results: list[GameAnalysisResult | None] = [None] * len(metadata_list)

    def work(idx: int, meta: GameMetadata) -> tuple[int, GameAnalysisResult]:
        logger.info("Analyzing game %s (%s)", meta.game_id, meta.user_color)
        eng = engine_pool.get()
        try:
            result = GameAnalyzer(eng, settings).analyze(meta)
            return idx, result
        finally:
            engine_pool.put(eng)

    try:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(work, i, meta) for i, meta in enumerate(metadata_list)
            ]
            for fut in as_completed(futures):
                idx, result = fut.result()
                results[idx] = result
                write_game_json(result, games_dir / f"{result.metadata.game_id}.json")
    finally:
        if owns_engines:
            for eng in pool_engines:
                eng.close()

    return [r for r in results if r is not None]


def analyze_game_batch(
    metadata_list: list[GameMetadata],
    *,
    settings: AnalysisSettings,
    games_dir: Path,
    engine: EngineAdapter | None = None,
    workers: int | None = None,
    warnings: list[str] | None = None,
) -> list[GameAnalysisResult]:
    """Analyze games, preferring parallel Stockfish workers with sequential fallback.

    When ``engine`` is injected (tests / offline), analysis is always sequential.
    When ``workers > 1`` and no engine is injected, starts a pool of Stockfish
    processes; on failure, warns and falls back to a single sequential engine.
    """
    warn = warnings if warnings is not None else []
    worker_count = max(1, workers if workers is not None else settings.workers)

    if engine is not None or worker_count == 1 or len(metadata_list) <= 1:
        if engine is not None:
            return _analyze_games_sequential(metadata_list, engine, settings, games_dir)
        sequential = StockfishEngine.from_settings(settings)
        sequential.open()
        try:
            return _analyze_games_sequential(metadata_list, sequential, settings, games_dir)
        finally:
            sequential.close()

    try:
        logger.info("Analyzing with %d parallel Stockfish worker(s)", worker_count)
        return _analyze_games_parallel(metadata_list, settings, worker_count, games_dir)
    except EngineError as exc:
        msg = f"Parallel analysis failed ({exc}); falling back to sequential"
        logger.warning(msg)
        warn.append(msg)
        sequential = StockfishEngine.from_settings(settings)
        sequential.open()
        try:
            return _analyze_games_sequential(metadata_list, sequential, settings, games_dir)
        finally:
            sequential.close()


def _maybe_attach_coaching(
    report: AnalysisReport,
    *,
    settings: AnalysisSettings,
    coach: bool,
    coaching_provider: CoachingProvider | None,
    warnings: list[str],
    prior_profile: PlayerCoachingProfile | None = None,
) -> AnalysisReport:
    """Attach optional LLM coaching; soft-fail into warnings on error."""
    if not coach and coaching_provider is None:
        return report

    provider = coaching_provider
    owns_provider = False
    try:
        if provider is None:
            provider = OpenAICoachingProvider.from_settings(settings)
            owns_provider = True
        logger.info("Generating OpenAI coaching (%s)", settings.openai_model)
        coaching = provider.coach(report, prior_profile=prior_profile)
        report.coaching = coaching
        report.settings.coaching_enabled = True
        report.settings.coaching_model = coaching.model
    except CoachingError as exc:
        msg = f"Coaching skipped: {exc}"
        logger.warning(msg)
        warnings.append(msg)
        report.warnings = warnings
        report.settings.coaching_enabled = False
        report.settings.coaching_model = None
        report.coaching = None
    finally:
        if owns_provider and isinstance(provider, OpenAICoachingProvider):
            provider.close()
    return report


def _persist_player_profile(
    report: AnalysisReport,
    *,
    settings: AnalysisSettings,
    report_path: Path,
) -> Path | None:
    """Merge coaching/habits into durable player profile; return profile path."""
    players_dir = Path(settings.default_players_dir)
    path = profile_path(players_dir, report.settings.username, report.settings.platform)
    existing = load_profile(path)
    updated = merge_profile(existing, report, report_path=report_path)
    save_profile(updated, path)
    logger.info("Updated player coaching profile: %s", path)
    return path


def resolve_report_json_path(report_ref: Path) -> Path:
    """Accept a report directory or analysis.json path."""
    path = Path(report_ref)
    if path.is_dir():
        candidate = path / "analysis.json"
        if not candidate.is_file():
            raise FileNotFoundError(f"No analysis.json in report directory: {path}")
        return candidate
    if path.name != "analysis.json" and path.is_file():
        # Allow passing report.html's sibling implicitly if mis-specified? keep strict.
        pass
    if not path.is_file():
        raise FileNotFoundError(f"Report not found: {path}")
    return path


def recoach_from_report(
    report_ref: Path,
    *,
    settings: AnalysisSettings | None = None,
    coaching_provider: CoachingProvider | None = None,
    use_llm: bool = True,
    refresh_habits: bool = True,
) -> tuple[AnalysisReport, Path, Path | None]:
    """Re-coach from a saved analysis.json without re-running Stockfish.

    Returns ``(report, analysis_json_path, profile_path_or_none)``.
    """
    settings = settings or AnalysisSettings()
    analysis_path = resolve_report_json_path(report_ref)
    run_dir = analysis_path.parent
    report = load_analysis_json(analysis_path)
    warnings = list(report.warnings)

    if refresh_habits:
        report.habits = analyze_habits(report.games, report.overall, settings)
        report.tactics = analyze_piece_and_tactics(report.games)

    profile_file = profile_path(
        Path(settings.default_players_dir),
        report.settings.username,
        report.settings.platform,
    )
    prior = load_profile(profile_file)

    if use_llm:
        report = _maybe_attach_coaching(
            report,
            settings=settings,
            coach=True,
            coaching_provider=coaching_provider,
            warnings=warnings,
            prior_profile=prior,
        )
    report.warnings = warnings

    write_analysis_json(report, analysis_path)
    write_html_report(report, report.settings.username, run_dir / "report.html")
    profile_out = _persist_player_profile(report, settings=settings, report_path=analysis_path)
    return report, analysis_path, profile_out


class AnalysisPipeline:
    """Download → analyze → aggregate → write reports."""

    def __init__(
        self,
        *,
        game_source: GameSource | None = None,
        chess_com: ChessComClient | None = None,
        engine: EngineAdapter | None = None,
        settings: AnalysisSettings | None = None,
        coaching_provider: CoachingProvider | None = None,
    ) -> None:
        self.settings = settings or AnalysisSettings()
        # chess_com kept for backward-compatible injection in tests.
        self._game_source = game_source or chess_com
        self._engine = engine
        self._coaching_provider = coaching_provider
        self._owns_game_source = game_source is None and chess_com is None
        self._owns_engine = engine is None

    def run(
        self,
        username: str,
        *,
        games: int = 10,
        platform: str = "chess.com",
        time_control: TimeControlFilter | None = None,
        output_dir: Path | None = None,
        coach: bool = False,
    ) -> tuple[AnalysisReport, Path]:
        settings = self.settings
        platform_name = normalize_platform(platform)
        out_root = Path(output_dir or settings.default_output_dir)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_dir = out_root / f"{username.lower()}-{stamp}"
        games_dir = run_dir / "games"
        assets_dir = run_dir / "assets"
        games_dir.mkdir(parents=True, exist_ok=True)
        assets_dir.mkdir(parents=True, exist_ok=True)

        client: GameSource = self._game_source or create_game_source(
            platform_name,
            settings=settings,
        )

        warnings: list[str] = []
        try:
            metadata_list, fetch_warnings = client.fetch_recent_games(
                username,
                limit=games,
                time_control=time_control,
            )
            warnings.extend(fetch_warnings)

            for meta in metadata_list:
                (games_dir / f"{meta.game_id}.pgn").write_text(meta.pgn, encoding="utf-8")

            analyzed = analyze_game_batch(
                metadata_list,
                settings=settings,
                games_dir=games_dir,
                engine=self._engine,
                workers=settings.workers,
                warnings=warnings,
            )

            overall = aggregate_stats(analyzed, settings)
            habits = analyze_habits(analyzed, overall, settings)
            tactics = analyze_piece_and_tactics(analyzed)
            stockfish_path = settings.resolve_stockfish_path() or "unknown"
            if isinstance(self._engine, StockfishEngine):
                stockfish_path = self._engine.path

            report = AnalysisReport(
                settings=AnalysisRunSettings(
                    username=username,
                    games_requested=games,
                    games_found=len(analyzed),
                    platform=platform_name,
                    time_control_filter=time_control,
                    stockfish_path=stockfish_path,
                    depth=settings.depth,
                    multipv=settings.multipv,
                    pv_moves=settings.pv_moves,
                    inaccuracy_threshold=settings.inaccuracy_threshold,
                    mistake_threshold=settings.mistake_threshold,
                    blunder_threshold=settings.blunder_threshold,
                    max_critical_positions=settings.max_critical_positions,
                    analyzed_at=datetime.now(UTC),
                    coaching_enabled=False,
                    coaching_model=None,
                ),
                overall=overall,
                games=analyzed,
                warnings=warnings,
                habits=habits,
                tactics=tactics,
            )

            prior = load_profile(
                profile_path(
                    Path(settings.default_players_dir),
                    username,
                    platform_name,
                )
            )
            report = _maybe_attach_coaching(
                report,
                settings=settings,
                coach=coach,
                coaching_provider=self._coaching_provider,
                warnings=warnings,
                prior_profile=prior,
            )

            analysis_path = run_dir / "analysis.json"
            write_analysis_json(report, analysis_path)
            write_html_report(report, username, run_dir / "report.html")
            if coach or report.coaching is not None or report.habits is not None:
                _persist_player_profile(
                    report,
                    settings=settings,
                    report_path=analysis_path,
                )
            return report, run_dir
        finally:
            if self._owns_game_source:
                client.close()


def analyze_games_offline(
    username: str,
    games_meta: list[GameMetadata],
    engine: EngineAdapter,
    *,
    settings: AnalysisSettings | None = None,
    output_dir: Path,
    games_requested: int | None = None,
    platform: str = "chess.com",
    time_control: str | None = None,
    warnings: list[str] | None = None,
    coach: bool = False,
    coaching_provider: CoachingProvider | None = None,
    persist_profile: bool = False,
) -> tuple[AnalysisReport, Path]:
    """Run analysis from preloaded games (for tests / offline fixtures)."""
    settings = settings or AnalysisSettings()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / f"{username.lower()}-{stamp}"
    games_dir = run_dir / "games"
    (run_dir / "assets").mkdir(parents=True, exist_ok=True)
    games_dir.mkdir(parents=True, exist_ok=True)

    warn = list(warnings or [])
    for meta in games_meta:
        (games_dir / f"{meta.game_id}.pgn").write_text(meta.pgn, encoding="utf-8")

    analyzed = analyze_game_batch(
        games_meta,
        settings=settings,
        games_dir=games_dir,
        engine=engine,
        workers=1,
        warnings=warn,
    )

    overall = aggregate_stats(analyzed, settings)
    habits = analyze_habits(analyzed, overall, settings)
    tactics = analyze_piece_and_tactics(analyzed)
    path = settings.resolve_stockfish_path() or "mock"
    report = AnalysisReport(
        settings=AnalysisRunSettings(
            username=username,
            games_requested=games_requested or len(games_meta),
            games_found=len(analyzed),
            platform=platform,
            time_control_filter=time_control,
            stockfish_path=path,
            depth=settings.depth,
            multipv=settings.multipv,
            pv_moves=settings.pv_moves,
            inaccuracy_threshold=settings.inaccuracy_threshold,
            mistake_threshold=settings.mistake_threshold,
            blunder_threshold=settings.blunder_threshold,
            max_critical_positions=settings.max_critical_positions,
            analyzed_at=datetime.now(UTC),
            coaching_enabled=False,
            coaching_model=None,
        ),
        overall=overall,
        games=analyzed,
        warnings=warn,
        habits=habits,
        tactics=tactics,
    )
    prior = None
    if coach or persist_profile:
        prior = load_profile(
            profile_path(Path(settings.default_players_dir), username, platform)
        )
    report = _maybe_attach_coaching(
        report,
        settings=settings,
        coach=coach,
        coaching_provider=coaching_provider,
        warnings=warn,
        prior_profile=prior,
    )
    analysis_path = run_dir / "analysis.json"
    write_analysis_json(report, analysis_path)
    write_html_report(report, username, run_dir / "report.html")
    if persist_profile or coach or report.coaching is not None:
        _persist_player_profile(report, settings=settings, report_path=analysis_path)
    return report, run_dir
