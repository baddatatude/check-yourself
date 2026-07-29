"""Piece-level and tactical-motif analysis from PGNs + Stockfish-tagged errors."""

from __future__ import annotations

from collections import Counter, defaultdict
from io import StringIO

import chess
import chess.pgn

from check_yourself.models import (
    GameAnalysisResult,
    HabitExample,
    MoveAnalysis,
    PieceCount,
    TacticCount,
    TacticExample,
    TacticKind,
    TacticsReport,
)

PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 100,
}


def _piece_name(piece_type: chess.PieceType | None) -> str:
    if piece_type is None:
        return "unknown"
    return PIECE_NAMES.get(piece_type, "unknown")


def _player_color(game: GameAnalysisResult) -> chess.Color:
    return chess.WHITE if game.metadata.user_color == "white" else chess.BLACK


def _counts_from_counter(counter: Counter[str], *, total_hint: int | None = None) -> list[PieceCount]:
    total = total_hint if total_hint is not None else sum(counter.values())
    rows: list[PieceCount] = []
    for name, count in counter.most_common():
        rows.append(
            PieceCount(
                piece=name,
                count=count,
                share=round(count / total, 4) if total else 0.0,
            )
        )
    return rows


def _moved_piece_name(move: MoveAnalysis) -> str:
    try:
        board = chess.Board(move.fen_before)
        mv = chess.Move.from_uci(move.played_uci)
        piece = board.piece_at(mv.from_square)
        return _piece_name(piece.piece_type if piece else None)
    except (ValueError, chess.InvalidMoveError):
        return "unknown"


def _mating_piece_against_player(game: GameAnalysisResult) -> str | None:
    """Return piece type that delivered checkmate against the player, if any."""
    outcome = game.metadata.result
    # Need a loss; mate may be encoded in PGN result or terminal position
    player = game.metadata.user_color
    if player == "white" and outcome not in {"0-1", "0–1"}:
        # still inspect board — resignations aren't mates
        pass
    if player == "black" and outcome not in {"1-0", "1–0"}:
        pass

    try:
        pgn_game = chess.pgn.read_game(StringIO(game.metadata.pgn))
    except Exception:
        return None
    if pgn_game is None:
        return None

    board = pgn_game.board()
    last_move: chess.Move | None = None
    node: chess.pgn.GameNode = pgn_game
    while node.variations:
        node = node.variation(0)
        last_move = node.move
        board.push(last_move)

    if last_move is None or not board.is_checkmate():
        return None

    # Side to move is the mated side
    mated_color = board.turn
    player_color = _player_color(game)
    if mated_color != player_color:
        return None  # player delivered mate

    # Mating piece sits on the destination of the last move (or pawn promo)
    piece = board.piece_at(last_move.to_square)
    if piece is None:
        return None
    return _piece_name(piece.piece_type)


def _ray_behind(board: chess.Board, slider: chess.Square, first_hit: chess.Square) -> chess.Square | None:
    """Next occupied square beyond ``first_hit`` on the ray from ``slider``."""
    sf, sr = chess.square_file(slider), chess.square_rank(slider)
    ff, fr = chess.square_file(first_hit), chess.square_rank(first_hit)
    df = ff - sf
    dr = fr - sr
    if df == 0 and dr == 0:
        return None
    step_f = 0 if df == 0 else (1 if df > 0 else -1)
    step_r = 0 if dr == 0 else (1 if dr > 0 else -1)
    # Must be a queen/rook/bishop ray
    if step_f != 0 and step_r != 0 and abs(df) != abs(dr):
        return None
    if step_f == 0 and step_r == 0:
        return None
    f, r = ff + step_f, fr + step_r
    while 0 <= f <= 7 and 0 <= r <= 7:
        sq = chess.square(f, r)
        if board.piece_at(sq) is not None:
            return sq
        f += step_f
        r += step_r
    return None


def _move_gives_check(board: chess.Board, move: chess.Move) -> bool:
    board.push(move)
    check = board.is_check()
    board.pop()
    return check


def _classify_opponent_move(
    board_before: chess.Board,
    move: chess.Move,
    *,
    victim: chess.Color,
) -> list[TacticKind]:
    """Heuristic classification of an opponent move that may hurt ``victim``."""
    kinds: list[TacticKind] = []
    attacker = not victim
    if board_before.turn != attacker:
        return kinds

    # Discovered attack / discovered check: something other than the mover newly attacks
    before_attacks: dict[chess.Square, set[chess.Square]] = {}
    for sq in chess.SQUARES:
        piece = board_before.piece_at(sq)
        if piece is None or piece.color != attacker or sq == move.from_square:
            continue
        before_attacks[sq] = {
            t
            for t in board_before.attacks(sq)
            if (tp := board_before.piece_at(t)) is not None and tp.color == victim
        }

    board_before.push(move)
    try:
        mover_sq = move.to_square
        mover_piece = board_before.piece_at(mover_sq)

        # Fork: moved piece attacks 2+ valuable enemy units (king counts)
        if mover_piece is not None:
            targets: list[tuple[chess.Square, int, int]] = []
            for t in board_before.attacks(mover_sq):
                tp = board_before.piece_at(t)
                if tp is None or tp.color != victim:
                    continue
                targets.append(
                    (t, tp.piece_type, PIECE_VALUES.get(tp.piece_type, 0))
                )
            if len(targets) >= 2:
                vals = sorted((v for _, _, v in targets), reverse=True)
                types = {pt for _, pt, _ in targets}
                king_fork = chess.KING in types and len(targets) >= 2
                double_minor = vals[0] >= 3 and vals[1] >= 3
                if king_fork or double_minor:
                    kinds.append(TacticKind.FORK)

        # Pin / skewer along slider rays from mover (or any new slider alignment)
        sliders: list[chess.Square] = []
        if mover_piece and mover_piece.piece_type in {
            chess.BISHOP,
            chess.ROOK,
            chess.QUEEN,
        }:
            sliders.append(mover_sq)
        for sq in chess.SQUARES:
            piece = board_before.piece_at(sq)
            if (
                piece
                and piece.color == attacker
                and piece.piece_type in {chess.BISHOP, chess.ROOK, chess.QUEEN}
            ):
                if sq not in sliders:
                    sliders.append(sq)

        # Prefer motifs created/used by the reply move itself
        for slider in sliders:
            # Only attribute pin/skewer if this reply is the slider move
            # or the reply unmasked this slider (discovered) — keep simple: slider == mover
            if slider != mover_sq:
                continue
            for t in board_before.attacks(slider):
                front = board_before.piece_at(t)
                if front is None or front.color != victim:
                    continue
                behind = _ray_behind(board_before, slider, t)
                if behind is None:
                    continue
                back = board_before.piece_at(behind)
                if back is None or back.color != victim:
                    continue
                fv = PIECE_VALUES.get(front.piece_type, 0)
                bv = PIECE_VALUES.get(back.piece_type, 0)
                if back.piece_type == chess.KING or bv > fv:
                    if TacticKind.PIN not in kinds:
                        kinds.append(TacticKind.PIN)
                if fv >= 5 and bv >= 1 and fv > bv:
                    if TacticKind.SKEWER not in kinds:
                        kinds.append(TacticKind.SKEWER)

        # Discovered attack: a non-moving piece newly attacks a victim unit
        for sq, old_targets in before_attacks.items():
            piece = board_before.piece_at(sq)
            if piece is None or piece.color != attacker:
                continue
            new_targets = {
                t
                for t in board_before.attacks(sq)
                if (tp := board_before.piece_at(t)) is not None and tp.color == victim
            }
            gained = new_targets - old_targets
            if not gained:
                continue
            # Meaningful if checks or hits piece value >= knight
            if board_before.is_check() and sq != mover_sq:
                if TacticKind.DISCOVERED_ATTACK not in kinds:
                    kinds.append(TacticKind.DISCOVERED_ATTACK)
                continue
            for t in gained:
                tp = board_before.piece_at(t)
                if tp and PIECE_VALUES.get(tp.piece_type, 0) >= 3:
                    if TacticKind.DISCOVERED_ATTACK not in kinds:
                        kinds.append(TacticKind.DISCOVERED_ATTACK)
                    break
    finally:
        board_before.pop()

    return kinds


def _tactics_after_player_error(
    move: MoveAnalysis,
    *,
    player: chess.Color,
) -> list[tuple[TacticKind, chess.Move]]:
    """Opponent replies that create fork/pin/skewer/discovered attack after an error."""
    try:
        board = chess.Board(move.fen_before)
        board.push(chess.Move.from_uci(move.played_uci))
    except (ValueError, chess.InvalidMoveError):
        return []

    if board.is_game_over():
        return []

    found: list[tuple[TacticKind, chess.Move]] = []
    # Prefer checking / capturing replies first for speed
    replies = sorted(
        board.legal_moves,
        key=lambda m: (
            0 if _move_gives_check(board, m) else 1,
            0 if board.is_capture(m) else 1,
        ),
    )
    seen: set[TacticKind] = set()
    for reply in replies[:40]:
        kinds = _classify_opponent_move(board, reply, victim=player)
        for kind in kinds:
            if kind in seen:
                continue
            seen.add(kind)
            found.append((kind, reply))
        if len(seen) >= 4:
            break
    return found


def analyze_piece_and_tactics(
    games: list[GameAnalysisResult],
    *,
    max_examples_per_tactic: int = 4,
) -> TacticsReport:
    """Summarize mating pieces, blunder pieces, and tactics that hurt the player."""
    notes: list[str] = []
    mate_counter: Counter[str] = Counter()
    blunder_counter: Counter[str] = Counter()
    blunder_loss: dict[str, int] = defaultdict(int)
    tactic_counter: Counter[str] = Counter()
    tactic_examples: dict[str, list[TacticExample]] = defaultdict(list)
    games_with_mate = 0
    errors_scanned = 0

    for game in games:
        mate_piece = _mating_piece_against_player(game)
        if mate_piece:
            mate_counter[mate_piece] += 1
            games_with_mate += 1

        player = _player_color(game)
        for move in game.moves:
            if move.quality == "blunder":
                pname = _moved_piece_name(move)
                blunder_counter[pname] += 1
                blunder_loss[pname] += min(move.eval_loss_cp, 800)

            if move.quality not in {"blunder", "mistake"}:
                continue
            errors_scanned += 1
            hits = _tactics_after_player_error(move, player=player)
            for kind, reply in hits:
                key = kind.value
                tactic_counter[key] += 1
                if len(tactic_examples[key]) >= max_examples_per_tactic:
                    continue
                try:
                    board = chess.Board(move.fen_before)
                    board.push(chess.Move.from_uci(move.played_uci))
                    fen_after = board.fen()
                    reply_san = board.san(reply)
                except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError):
                    fen_after = move.fen_before
                    reply_san = reply.uci()
                tactic_examples[key].append(
                    TacticExample(
                        kind=kind,
                        game_id=move.game_id,
                        ply=move.ply,
                        fullmove_number=move.fullmove_number,
                        fen=move.fen_before,
                        fen_after_error=fen_after,
                        played_san=move.played_san,
                        played_uci=move.played_uci,
                        preferred_san=move.preferred_san,
                        preferred_uci=move.preferred_uci,
                        opponent_reply_san=reply_san,
                        opponent_reply_uci=reply.uci(),
                        eval_loss_cp=move.eval_loss_cp,
                        quality=move.quality,
                        phase=move.game_phase,
                        player_color=move.player_color,
                        note=(
                            f"After {move.played_san}, opponent can hurt you with a "
                            f"{kind.value.replace('_', ' ')} ({reply_san})."
                        ),
                    )
                )

    blunder_total = sum(blunder_counter.values())
    blunder_counts = _counts_from_counter(blunder_counter, total_hint=blunder_total)
    for row in blunder_counts:
        row.total_eval_loss_cp = int(blunder_loss.get(row.piece, 0))

    mate_total = sum(mate_counter.values())
    mate_counts = _counts_from_counter(mate_counter, total_hint=mate_total)

    tactic_rows: list[TacticCount] = []
    for kind, count in tactic_counter.most_common():
        tactic_rows.append(
            TacticCount(
                kind=TacticKind(kind),
                count=count,
                share=round(count / errors_scanned, 4) if errors_scanned else 0.0,
                examples=tactic_examples.get(kind, []),
            )
        )

    if games_with_mate == 0:
        notes.append(
            "No checkmates against you in this sample (losses may be resignations or timeouts)."
        )
    if blunder_total == 0:
        notes.append("No blunders tagged in this sample for piece breakdown.")
    if not tactic_rows:
        notes.append(
            "No clear fork/pin/skewer/discovered-attack replies found after mistakes/blunders."
        )
    else:
        notes.append(
            "Tactics are geometric heuristics on opponent replies after your mistakes/blunders — "
            "not an exhaustive puzzle engine."
        )

    return TacticsReport(
        games_analyzed=len(games),
        games_checkmated=games_with_mate,
        errors_scanned=errors_scanned,
        mated_by_piece=mate_counts,
        blunders_by_piece=blunder_counts,
        tactics_that_hurt=tactic_rows,
        notes=notes,
    )


def tactics_brief_for_coaching(tactics: TacticsReport) -> dict[str, object]:
    return {
        "games_analyzed": tactics.games_analyzed,
        "games_checkmated": tactics.games_checkmated,
        "mated_by_piece": [c.model_dump() for c in tactics.mated_by_piece],
        "blunders_by_piece": [c.model_dump() for c in tactics.blunders_by_piece],
        "tactics_that_hurt": [
            {
                "kind": t.kind.value,
                "count": t.count,
                "share_of_errors": t.share,
                "examples": [
                    {
                        "game_id": ex.game_id,
                        "move": ex.fullmove_number,
                        "played": ex.played_san,
                        "opponent_reply": ex.opponent_reply_san,
                        "fen": ex.fen,
                        "note": ex.note,
                    }
                    for ex in t.examples[:3]
                ],
            }
            for t in tactics.tactics_that_hurt
        ],
        "notes": tactics.notes,
    }


def habit_examples_from_tactics(tactics: TacticsReport) -> list[HabitExample]:
    """Optional bridge for walkthroughs that expect HabitExample-like boards."""
    out: list[HabitExample] = []
    for row in tactics.tactics_that_hurt:
        for ex in row.examples:
            out.append(
                HabitExample(
                    game_id=ex.game_id,
                    ply=ex.ply,
                    fullmove_number=ex.fullmove_number,
                    fen=ex.fen,
                    played_san=ex.played_san,
                    preferred_san=ex.preferred_san,
                    played_uci=ex.played_uci,
                    preferred_uci=ex.preferred_uci,
                    eval_loss_cp=ex.eval_loss_cp,
                    quality=ex.quality,
                    phase=ex.phase,
                    note=ex.note,
                    player_color=ex.player_color,
                )
            )
    return out
