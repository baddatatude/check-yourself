"""Plotly chart builders for the HTML report (CDN-free embeds)."""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

from check_yourself.models import AnalysisReport, GameAnalysisResult, OverallStats


def _fig_to_html(fig: go.Figure, *, include_js: bool = False) -> str:
    html = fig.to_html(
        full_html=False,
        include_plotlyjs="cdn" if include_js else False,
        config={"displayModeBar": False, "responsive": True},
    )
    return str(html)


def embed_plotly_js() -> str:
    """Return Plotly JS bundle for offline self-contained reports."""
    from plotly.offline import get_plotlyjs

    return str(get_plotlyjs())


def evaluation_graph(game: GameAnalysisResult) -> go.Figure:
    xs = [p["fullmove_number"] for p in game.eval_graph]
    ys = [p["eval"] for p in game.eval_graph]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="lines+markers",
            name="Eval (player POV)",
            line={"color": "#1f4e79", "width": 2},
            marker={"size": 6},
        )
    )
    fig.add_hline(y=0, line_dash="dot", line_color="#888")
    fig.update_layout(
        title=f"Evaluation — game {game.metadata.game_id}",
        xaxis_title="Move number",
        yaxis_title="Evaluation (cp, player POV)",
        template="plotly_white",
        height=320,
        margin={"l": 50, "r": 20, "t": 50, "b": 40},
    )
    return fig


def eval_loss_by_move_number(report: AnalysisReport) -> go.Figure:
    buckets: dict[int, list[int]] = {}
    for game in report.games:
        for move in game.moves:
            buckets.setdefault(move.fullmove_number, []).append(move.eval_loss_cp)
    xs = sorted(buckets)
    ys = [sum(buckets[x]) / len(buckets[x]) for x in xs]
    fig = go.Figure(go.Bar(x=xs, y=ys, marker_color="#c45c26"))
    fig.update_layout(
        title="Average evaluation loss by move number",
        xaxis_title="Move number",
        yaxis_title="Average eval loss (cp)",
        template="plotly_white",
        height=340,
        margin={"l": 50, "r": 20, "t": 50, "b": 40},
    )
    return fig


def inaccuracies_mistakes_blunders_by_phase(report: AnalysisReport) -> go.Figure:
    counts = {
        "opening": {"inaccuracy": 0, "mistake": 0, "blunder": 0},
        "middlegame": {"inaccuracy": 0, "mistake": 0, "blunder": 0},
        "endgame": {"inaccuracy": 0, "mistake": 0, "blunder": 0},
    }
    for game in report.games:
        for move in game.moves:
            if move.quality in counts[move.game_phase]:
                counts[move.game_phase][move.quality] += 1
    phases = ["opening", "middlegame", "endgame"]
    fig = go.Figure()
    for quality, color in (
        ("inaccuracy", "#f0c040"),
        ("mistake", "#e67e22"),
        ("blunder", "#c0392b"),
    ):
        fig.add_trace(
            go.Bar(
                name=quality.title(),
                x=phases,
                y=[counts[p][quality] for p in phases],
                marker_color=color,
            )
        )
    fig.update_layout(
        barmode="group",
        title="Inaccuracies, mistakes, and blunders by game phase",
        template="plotly_white",
        height=340,
        margin={"l": 50, "r": 20, "t": 50, "b": 40},
    )
    return fig


def results_by_color(stats: OverallStats) -> go.Figure:
    colors = ["white", "black"]
    win_vals = []
    loss_vals = []
    draw_vals = []
    for c in colors:
        rec = stats.results_by_color.get(c)
        win_vals.append(rec.wins if rec else 0)
        loss_vals.append(rec.losses if rec else 0)
        draw_vals.append(rec.draws if rec else 0)
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Wins", x=colors, y=win_vals, marker_color="#2e7d32"))
    fig.add_trace(go.Bar(name="Draws", x=colors, y=draw_vals, marker_color="#757575"))
    fig.add_trace(go.Bar(name="Losses", x=colors, y=loss_vals, marker_color="#c62828"))
    fig.update_layout(
        barmode="stack",
        title="Results by color",
        template="plotly_white",
        height=340,
        margin={"l": 50, "r": 20, "t": 50, "b": 40},
    )
    return fig


def eval_loss_by_phase(stats: OverallStats) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=[p.phase for p in stats.by_phase],
            y=[p.total_eval_loss for p in stats.by_phase],
            marker_color="#1f4e79",
        )
    )
    fig.update_layout(
        title="Total evaluation loss by game phase",
        yaxis_title="Total eval loss (cp)",
        template="plotly_white",
        height=340,
        margin={"l": 50, "r": 20, "t": 50, "b": 40},
    )
    return fig


def per_game_acpl(report: AnalysisReport) -> go.Figure:
    ids = [g.metadata.game_id for g in report.games]
    vals = [g.average_centipawn_loss for g in report.games]
    fig = go.Figure(go.Bar(x=ids, y=vals, marker_color="#5c6bc0"))
    fig.update_layout(
        title="Per-game average centipawn loss",
        xaxis_title="Game ID",
        yaxis_title="ACPL",
        template="plotly_white",
        height=340,
        margin={"l": 50, "r": 20, "t": 50, "b": 80},
    )
    return fig


def opening_comparison(stats: OverallStats) -> go.Figure | None:
    openings = [o for o in stats.by_opening if o.opening != "Unknown"]
    if len(openings) < 2:
        return None
    fig = go.Figure(
        go.Bar(
            x=[o.opening for o in openings[:12]],
            y=[o.average_centipawn_loss for o in openings[:12]],
            marker_color="#00838f",
            text=["*" if o.small_sample else "" for o in openings[:12]],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Opening comparison (ACPL; * = small sample)",
        yaxis_title="Average centipawn loss",
        template="plotly_white",
        height=380,
        margin={"l": 50, "r": 20, "t": 50, "b": 120},
    )
    return fig


def piece_bar_chart(
    rows: list[Any],
    *,
    title: str,
    value_attr: str = "count",
    color: str = "#1f4e79",
) -> go.Figure | None:
    if not rows:
        return None
    labels: list[str] = []
    for r in rows:
        label = getattr(r, "piece", None)
        if label is None:
            kind = getattr(r, "kind", None)
            label = kind.value if hasattr(kind, "value") else kind
        labels.append(str(label).replace("_", " "))
    values = [getattr(r, value_attr) for r in rows]
    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=color))
    fig.update_layout(
        title=title,
        yaxis_title=value_attr.replace("_", " "),
        template="plotly_white",
        height=320,
        margin={"l": 50, "r": 20, "t": 50, "b": 60},
    )
    return fig


def build_chart_html_fragments(report: AnalysisReport) -> dict[str, Any]:
    """Build HTML fragments for all charts (Plotly JS embedded separately once)."""
    game_charts = {
        g.metadata.game_id: _fig_to_html(evaluation_graph(g)) for g in report.games
    }
    opening_fig = opening_comparison(report.overall)
    mated_fig = None
    blunder_piece_fig = None
    tactics_fig = None
    if report.tactics is not None:
        mated_fig = piece_bar_chart(
            report.tactics.mated_by_piece,
            title="Pieces that checkmated you",
            color="#8b1e1e",
        )
        blunder_piece_fig = piece_bar_chart(
            report.tactics.blunders_by_piece,
            title="Pieces you blundered with most",
            color="#c45c26",
        )
        tactics_fig = piece_bar_chart(
            report.tactics.tactics_that_hurt,
            title="Tactics that hurt you after errors",
            color="#1f4e79",
        )
    return {
        "eval_loss_by_move": _fig_to_html(eval_loss_by_move_number(report)),
        "mistakes_by_phase": _fig_to_html(inaccuracies_mistakes_blunders_by_phase(report)),
        "results_by_color": _fig_to_html(results_by_color(report.overall)),
        "eval_loss_by_phase": _fig_to_html(eval_loss_by_phase(report.overall)),
        "per_game_acpl": _fig_to_html(per_game_acpl(report)),
        "opening_comparison": _fig_to_html(opening_fig) if opening_fig else None,
        "mated_by_piece": _fig_to_html(mated_fig) if mated_fig else None,
        "blunders_by_piece": _fig_to_html(blunder_piece_fig) if blunder_piece_fig else None,
        "tactics_that_hurt": _fig_to_html(tactics_fig) if tactics_fig else None,
        "game_charts": game_charts,
    }
