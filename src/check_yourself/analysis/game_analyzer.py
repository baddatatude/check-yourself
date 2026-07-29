"""Per-game Stockfish analysis for the requested player's moves."""

from __future__ import annotations

import logging
from io import StringIO

import chess
import chess.pgn

from check_yourself.analysis.critical_positions import select_critical_positions
from check_yourself.analysis.game_phase import classify_game_phase
from check_yourself.config import AnalysisSettings, classify_cp_loss
from check_yourself.engine.evaluation import (
    capped_eval_loss_for_acpl,
    evaluation_loss_cp,
    preferred_vs_played_loss_cp,
    to_player_evaluation,
)
from check_yourself.engine.stockfish import EngineAdapter
from check_yourself.models import (
    GameAnalysisResult,
    GameMetadata,
    MoveAnalysis,
)

logger = logging.getLogger(__name__)


def _clock_from_comment(comment: str | None) -> str | None:
    if not comment:
        return None
    # Chess.com style: [%clk 0:05:12.3]
    if "[%clk" in comment:
        start = comment.index("[%clk") + 5
        end = comment.find("]", start)
        if end > start:
            return comment[start:end].strip()
    return None


class GameAnalyzer:
    """Analyze one game: only the requested player's moves are scored."""

    def __init__(
        self,
        engine: EngineAdapter,
        settings: AnalysisSettings | None = None,
    ) -> None:
        self.engine = engine
        self.settings = settings or AnalysisSettings()

    def analyze(self, metadata: GameMetadata) -> GameAnalysisResult:
        game = chess.pgn.read_game(StringIO(metadata.pgn))
        if game is None:
            raise ValueError(f"Could not parse PGN for game {metadata.game_id}")

        board = game.board()
        player_is_white = metadata.user_color == "white"
        moves: list[MoveAnalysis] = []
        eval_graph: list[dict[str, object]] = []
        ply = 0

        node: chess.pgn.GameNode = game
        while node.variations:
            next_node = node.variation(0)
            move = next_node.move
            ply += 1
            mover_is_white = board.turn == chess.WHITE
            is_player_move = mover_is_white == player_is_white

            if is_player_move:
                move_analysis = self._analyze_player_move(
                    board=board,
                    move=move,
                    ply=ply,
                    metadata=metadata,
                    clock=_clock_from_comment(next_node.comment),
                )
                moves.append(move_analysis)
                eval_graph.append(
                    {
                        "ply": ply,
                        "fullmove_number": move_analysis.fullmove_number,
                        "eval": move_analysis.eval_after.value
                        if move_analysis.eval_after.kind.value == "cp"
                        else (
                            1000
                            if move_analysis.eval_after.value > 0
                            else -1000
                        ),
                        "eval_kind": move_analysis.eval_after.kind.value,
                        "san": move_analysis.played_san,
                    }
                )

            board.push(move)
            node = next_node

        critical = select_critical_positions(moves, self.settings)
        # ACPL uses capped losses so mate-scale swings don't dominate the mean.
        losses = [capped_eval_loss_for_acpl(m.eval_loss_cp) for m in moves]
        acpl = sum(losses) / len(losses) if losses else 0.0

        return GameAnalysisResult(
            metadata=metadata,
            moves=moves,
            critical_positions=critical,
            average_centipawn_loss=round(acpl, 2),
            inaccuracy_count=sum(1 for m in moves if m.quality == "inaccuracy"),
            mistake_count=sum(1 for m in moves if m.quality == "mistake"),
            blunder_count=sum(1 for m in moves if m.quality == "blunder"),
            eval_graph=eval_graph,
        )

    def _analyze_player_move(
        self,
        *,
        board: chess.Board,
        move: chess.Move,
        ply: int,
        metadata: GameMetadata,
        clock: str | None,
    ) -> MoveAnalysis:
        settings = self.settings
        fen_before = board.fen()
        phase = classify_game_phase(board)
        played_san = board.san(move)
        played_uci = move.uci()
        mover = board.turn

        before = self.engine.analyse(board)
        preferred = before.best_move
        preferred_uci = preferred.uci() if preferred else None
        preferred_san = board.san(preferred) if preferred else None
        pv_sans: list[str] = []
        tmp = board.copy(stack=False)
        for pv_move in before.pv:
            try:
                if pv_move not in tmp.legal_moves:
                    break
                pv_sans.append(tmp.san(pv_move))
                tmp.push(pv_move)
            except (ValueError, AssertionError):
                break

        board_after = board.copy(stack=False)
        board_after.push(move)
        after = self.engine.analyse(board_after)

        # Prefer loss vs Stockfish's recommended continuation when available.
        # Fall back to before→after player-perspective loss otherwise.
        if preferred is not None and preferred != move:
            board_best = board.copy(stack=False)
            board_best.push(preferred)
            after_best = self.engine.analyse(board_best)
            loss = preferred_vs_played_loss_cp(
                after_best.white_eval, after.white_eval, mover
            )
        elif preferred is not None and preferred == move:
            loss = 0
        else:
            loss = evaluation_loss_cp(before.white_eval, after.white_eval, mover)
        quality = classify_cp_loss(
            loss,
            excellent=settings.excellent_threshold,
            good=settings.good_threshold,
            inaccuracy=settings.inaccuracy_threshold,
            mistake=settings.mistake_threshold,
        )
        # Map blunder threshold: classify_cp_loss treats > mistake as blunder;
        # optionally raise bar using blunder_threshold for "blunder" label.
        if loss >= settings.blunder_threshold:
            quality = "blunder"
        elif loss > settings.mistake_threshold:
            quality = "mistake"

        eval_before = to_player_evaluation(before.white_eval, metadata.user_color)
        eval_after = to_player_evaluation(after.white_eval, metadata.user_color)

        return MoveAnalysis(
            game_id=metadata.game_id,
            player_color=metadata.user_color,
            ply=ply,
            fullmove_number=board.fullmove_number,
            fen_before=fen_before,
            played_san=played_san,
            played_uci=played_uci,
            preferred_uci=preferred_uci,
            preferred_san=preferred_san,
            principal_variation=pv_sans,
            eval_before=eval_before,
            eval_after=eval_after,
            eval_loss_cp=loss,
            mate_before=before.white_eval.mate,
            mate_after=after.white_eval.mate,
            quality=quality,  # type: ignore[arg-type]
            game_phase=phase,
            result=metadata.result,
            time_control=metadata.time_control,
            time_class=metadata.time_class,
            opening=metadata.opening,
            eco=metadata.eco,
            clock=clock,
        )


def result_for_player(result: str, user_color: str) -> str:
    """Return 'win', 'loss', 'draw', or 'unknown' for the player."""
    if result == "1/2-1/2":
        return "draw"
    if result == "1-0":
        return "win" if user_color == "white" else "loss"
    if result == "0-1":
        return "win" if user_color == "black" else "loss"
    return "unknown"
