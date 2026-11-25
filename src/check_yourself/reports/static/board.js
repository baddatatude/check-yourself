/* Check Yourself — offline SVG chessboard + walkthrough / heatmap UI */
(function (global) {
  "use strict";

  var PIECES = {
    P: ["M16 37v-3l5-5v-6a5 5 0 1 1 6 0v6l5 5v3Z"],
    N: ["M10 39v-5c2-5 10-7 14-13l-7 2-6-4 9-10V6l6 4c9 1 12 8 12 17v12Z",
        "M22 15h1M13 33h23"],
    B: ["M12 39v-4l7-5v-5c-4-2-6-6-3-10l8-8 8 8c3 4 1 8-3 10v5l7 5v4Z",
        "M24 12l5 6M15 34h18"],
    R: ["M11 39v-5l5-5V19l-3-3V9h6v5h3V9h4v5h3V9h6v7l-3 3v10l5 5v5Z",
        "M16 19h16M14 34h20"],
    Q: ["M10 14l8 6 6-11 6 11 8-6-5 16 4 5v4H11v-4l4-5Z",
        "M15 30h18M13 35h22"],
    K: ["M21 5h6v5h6v5h-6v4c5-6 13-3 13 3 0 4-4 7-7 9l4 4v5H11v-5l4-4c-3-2-7-5-7-9 0-6 8-9 13-3v-4h-6v-5h6Z",
        "M15 31h18M13 35h22"],
  };
  var FILES = "abcdefgh";

  function parseFen(fen) {
    var board = {};
    var placement = (fen || "").split(/\s+/)[0] || "";
    var rank = 8;
    var file = 0;
    for (var i = 0; i < placement.length; i++) {
      var ch = placement[i];
      if (ch === "/") {
        rank -= 1;
        file = 0;
        continue;
      }
      if (ch >= "1" && ch <= "8") {
        file += ch.charCodeAt(0) - 48;
        continue;
      }
      if (PIECES[ch.toUpperCase()] && file < 8 && rank >= 1) {
        board[FILES[file] + rank] = ch;
        file += 1;
      }
    }
    return board;
  }

  function sqToXY(sq, orientation, size) {
    var file = FILES.indexOf(sq[0]);
    var rank = parseInt(sq[1], 10) - 1;
    var col = orientation === "black" ? 7 - file : file;
    var row = orientation === "black" ? rank : 7 - rank;
    return { x: col * size, y: row * size, col: col, row: row };
  }

  function arrowPath(from, to, orientation, size) {
    var a = sqToXY(from, orientation, size);
    var b = sqToXY(to, orientation, size);
    var x1 = a.x + size / 2;
    var y1 = a.y + size / 2;
    var x2 = b.x + size / 2;
    var y2 = b.y + size / 2;
    var dx = x2 - x1;
    var dy = y2 - y1;
    var len = Math.sqrt(dx * dx + dy * dy) || 1;
    var ux = dx / len;
    var uy = dy / len;
    // shorten so arrow tip sits inside destination square
    var tipX = x2 - ux * size * 0.28;
    var tipY = y2 - uy * size * 0.28;
    var baseX = tipX - ux * size * 0.28;
    var baseY = tipY - uy * size * 0.28;
    var px = -uy;
    var py = ux;
    var w = size * 0.16;
    return {
      line: "M " + (x1 + ux * size * 0.2) + " " + (y1 + uy * size * 0.2) +
            " L " + baseX + " " + baseY,
      head: "M " + tipX + " " + tipY +
            " L " + (baseX + px * w) + " " + (baseY + py * w) +
            " L " + (baseX - px * w) + " " + (baseY - py * w) + " Z",
    };
  }

  function maxHeat(map) {
    var m = 0;
    Object.keys(map || {}).forEach(function (k) {
      if (map[k] > m) m = map[k];
    });
    return m || 1;
  }

  function renderBoard(container, opts) {
    opts = opts || {};
    var size = opts.size || 44;
    var orientation = opts.orientation || "white";
    var board = parseFen(opts.fen || "");
    var heat = opts.heatmap || null;
    var heatMax = maxHeat(heat);
    var light = opts.light || "#f0d9b5";
    var dark = opts.dark || "#b58863";
    var w = size * 8;
    var svgNS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 " + w + " " + w);
    svg.setAttribute("width", String(opts.pixelWidth || w));
    svg.setAttribute("height", String(opts.pixelWidth || w));
    svg.setAttribute("class", "cy-board-svg");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Chess position");

    for (var row = 0; row < 8; row++) {
      for (var col = 0; col < 8; col++) {
        var fileIdx = orientation === "black" ? 7 - col : col;
        var rankIdx = orientation === "black" ? row : 7 - row;
        var sq = FILES[fileIdx] + (rankIdx + 1);
        var rect = document.createElementNS(svgNS, "rect");
        rect.setAttribute("x", String(col * size));
        rect.setAttribute("y", String(row * size));
        rect.setAttribute("width", String(size));
        rect.setAttribute("height", String(size));
        rect.setAttribute("fill", (row + col) % 2 === 0 ? light : dark);
        svg.appendChild(rect);

        if (heat && heat[sq]) {
          var intensity = Math.min(1, heat[sq] / heatMax);
          var overlay = document.createElementNS(svgNS, "rect");
          overlay.setAttribute("x", String(col * size));
          overlay.setAttribute("y", String(row * size));
          overlay.setAttribute("width", String(size));
          overlay.setAttribute("height", String(size));
          overlay.setAttribute(
            "fill",
            "rgba(200, 40, 40, " + (0.15 + intensity * 0.65).toFixed(3) + ")"
          );
          svg.appendChild(overlay);
          if (opts.showHeatCounts) {
            var t = document.createElementNS(svgNS, "text");
            t.setAttribute("x", String(col * size + size / 2));
            t.setAttribute("y", String(row * size + size * 0.72));
            t.setAttribute("text-anchor", "middle");
            t.setAttribute("font-size", String(Math.max(10, size * 0.28)));
            t.setAttribute("font-family", "IBM Plex Sans, Segoe UI, sans-serif");
            t.setAttribute("fill", "#4a1010");
            t.setAttribute("font-weight", "700");
            t.textContent = String(Math.round(heat[sq] * 10) / 10);
            svg.appendChild(t);
          }
        }
      }
    }

    if (opts.coordinates) {
      function coordinate(text, row, col, isFile) {
        var label = document.createElementNS(svgNS, "text");
        label.setAttribute("x", String((col + (isFile ? 0.82 : 0.06)) * size));
        label.setAttribute("y", String((row + (isFile ? 0.96 : 0.22)) * size));
        label.setAttribute("font-size", String(size * 0.17));
        label.setAttribute("font-family", "sans-serif");
        label.setAttribute("fill", (row + col) % 2 === 0 ? "#604022" : "#fff5e8");
        label.textContent = text;
        svg.appendChild(label);
      }
      for (var index = 0; index < 8; index++) {
        coordinate(FILES[orientation === "black" ? 7 - index : index], 7, index, true);
        coordinate(String(orientation === "black" ? index + 1 : 8 - index), index, 0, false);
      }
    }

    Object.keys(board).forEach(function (sq) {
      var piece = board[sq];
      var xy = sqToXY(sq, orientation, size);
      var design = PIECES[piece.toUpperCase()];
      var white = piece === piece.toUpperCase();
      var group = document.createElementNS(svgNS, "g");
      group.setAttribute("transform", "translate(" + xy.x + " " + xy.y + ") scale(" + (size / 48) + ")");
      design.forEach(function (path, detail) {
        var shape = document.createElementNS(svgNS, "path");
        shape.setAttribute("d", path);
        shape.setAttribute("fill", detail ? "none" : white ? "#fbf5e9" : "#26323a");
        shape.setAttribute("stroke", detail && !white ? "#b2b9b7" : "#26323a");
        shape.setAttribute("stroke-width", detail ? "1.35" : white ? "1.7" : "1.2");
        shape.setAttribute("stroke-linecap", "round");
        shape.setAttribute("stroke-linejoin", "round");
        group.appendChild(shape);
      });
      svg.appendChild(group);
    });

    function drawArrow(uci, color, opacity) {
      if (!uci || uci.length < 4) return;
      var from = uci.slice(0, 2);
      var to = uci.slice(2, 4);
      var path = arrowPath(from, to, orientation, size);
      var line = document.createElementNS(svgNS, "path");
      line.setAttribute("d", path.line);
      line.setAttribute("stroke", color);
      line.setAttribute("stroke-width", String(size * 0.12));
      line.setAttribute("stroke-linecap", "round");
      line.setAttribute("fill", "none");
      line.setAttribute("opacity", String(opacity));
      svg.appendChild(line);
      var head = document.createElementNS(svgNS, "path");
      head.setAttribute("d", path.head);
      head.setAttribute("fill", color);
      head.setAttribute("opacity", String(opacity));
      svg.appendChild(head);
    }

    if (opts.preferred_uci) drawArrow(opts.preferred_uci, "#2f6b4f", 0.9);
    if (opts.played_uci) drawArrow(opts.played_uci, "#b00020", 0.85);

    container.innerHTML = "";
    container.appendChild(svg);
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function initWalkthrough(root, payload) {
    var sequences = (payload && payload.sequences) || [];
    if (!sequences.length) {
      root.innerHTML = "<p class='muted'>No walkthrough sequences for this report.</p>";
      return;
    }

    var state = { seq: 0, step: 0 };
    var tabs = el("div", "cy-walk-tabs");
    var boardWrap = el("div", "cy-walk-board-wrap");
    var boardHost = el("div", "cy-walk-board");
    var meta = el("div", "cy-walk-meta");
    var nav = el("div", "cy-walk-nav");
    var prevBtn = el("button", "cy-btn", "← Prev");
    var nextBtn = el("button", "cy-btn", "Next →");
    var counter = el("span", "cy-walk-counter");
    prevBtn.type = "button";
    nextBtn.type = "button";
    nav.appendChild(prevBtn);
    nav.appendChild(counter);
    nav.appendChild(nextBtn);
    boardWrap.appendChild(boardHost);
    boardWrap.appendChild(nav);
    boardWrap.appendChild(meta);

    function currentSeq() {
      return sequences[state.seq];
    }

    function renderTabs() {
      tabs.innerHTML = "";
      sequences.forEach(function (seq, idx) {
        var btn = el("button", "cy-tab" + (idx === state.seq ? " active" : ""), seq.title);
        btn.type = "button";
        btn.addEventListener("click", function () {
          state.seq = idx;
          state.step = 0;
          paint();
        });
        tabs.appendChild(btn);
      });
    }

    function paint() {
      renderTabs();
      var seq = currentSeq();
      var step = seq.steps[state.step];
      counter.textContent = (state.step + 1) + " / " + seq.steps.length;
      prevBtn.disabled = state.step <= 0;
      nextBtn.disabled = state.step >= seq.steps.length - 1;
      renderBoard(boardHost, {
        fen: step.fen,
        orientation: step.orientation || "white",
        played_uci: step.played_uci,
        preferred_uci: step.preferred_uci,
        size: 48,
        pixelWidth: 360,
      });
      meta.innerHTML = "";
      var title = el("h3", null, seq.title);
      meta.appendChild(title);
      if (seq.summary) meta.appendChild(el("p", null, seq.summary));
      var moveLine = el("p", null, null);
      moveLine.appendChild(el("strong", null, "Game " + step.game_id));
      moveLine.append(" · move " + step.fullmove_number + " · played ");
      moveLine.appendChild(el("strong", "quality-blunder", step.played_san || "?"));
      if (step.preferred_san) {
        moveLine.append(" · preferred ");
        var preferred = el("strong", null, step.preferred_san);
        preferred.style.color = "#2f6b4f";
        moveLine.appendChild(preferred);
      }
      moveLine.append(" · loss " + step.eval_loss_cp + " cp · ");
      moveLine.appendChild(el("span", "quality-" + step.quality, step.quality));
      meta.appendChild(moveLine);
      meta.appendChild(el("p", null, step.caption || ""));
      if (step.coach_note) {
        var coach = el("div", "coach");
        coach.appendChild(el("p", null, "Coach: " + step.coach_note));
        meta.appendChild(coach);
      }
      if (seq.practice_hint) {
        meta.appendChild(el("p", "muted", "Practice: " + seq.practice_hint));
      }
      var legend = el("p", "muted cy-arrow-legend", null);
      legend.innerHTML =
        "<span class='cy-swatch cy-swatch-played'></span> played &nbsp; " +
        "<span class='cy-swatch cy-swatch-pref'></span> Stockfish preferred";
      meta.appendChild(legend);
    }

    prevBtn.addEventListener("click", function () {
      if (state.step > 0) {
        state.step -= 1;
        paint();
      }
    });
    nextBtn.addEventListener("click", function () {
      if (state.step < currentSeq().steps.length - 1) {
        state.step += 1;
        paint();
      }
    });

    root.innerHTML = "";
    root.appendChild(tabs);
    root.appendChild(boardWrap);
    paint();
  }

  function initHeatmap(root, payload) {
    var maps = (payload && payload.heatmaps) || {};
    var labels = (payload && payload.heatmap_labels) || {};
    var keys = Object.keys(maps).filter(function (k) {
      return maps[k] && Object.keys(maps[k]).length;
    });
    if (!keys.length) {
      root.innerHTML = "<p class='muted'>No heatmap data for this sample.</p>";
      return;
    }
    var state = { key: keys.indexOf("blunder_to") >= 0 ? "blunder_to" : keys[0] };
    var tabs = el("div", "cy-walk-tabs");
    var boardHost = el("div", "cy-heat-board");
    var blurb = el("p", "muted");

    function paint() {
      tabs.innerHTML = "";
      keys.forEach(function (k) {
        var btn = el("button", "cy-tab" + (k === state.key ? " active" : ""), labels[k] || k);
        btn.type = "button";
        btn.addEventListener("click", function () {
          state.key = k;
          paint();
        });
        tabs.appendChild(btn);
      });
      renderBoard(boardHost, {
        fen: "8/8/8/8/8/8/8/8 w - - 0 1",
        orientation: "white",
        heatmap: maps[state.key],
        showHeatCounts: true,
        size: 48,
        pixelWidth: 360,
      });
      blurb.textContent =
        "Squares colored by how often errors landed there (or left from there). " +
        "Darker = more frequent in this " + ((payload && payload.games_analyzed) || "") +
        " sample.";
    }

    root.innerHTML = "";
    root.appendChild(tabs);
    root.appendChild(boardHost);
    root.appendChild(blurb);
    paint();
  }

  function initInlineBoards(root) {
    var nodes = (root || document).querySelectorAll("[data-cy-board]");
    Array.prototype.forEach.call(nodes, function (node) {
      renderBoard(node, {
        fen: node.getAttribute("data-fen") || "",
        orientation: node.getAttribute("data-orientation") || "white",
        played_uci: node.getAttribute("data-played-uci") || null,
        preferred_uci: node.getAttribute("data-preferred-uci") || null,
        size: 36,
        pixelWidth: Number(node.getAttribute("data-width") || 260),
      });
    });
  }

  function initContinuations(timeline, navigate) {
    var panel = el("div", "cy-continuation");
    if (!timeline.continuations.length) return panel;
    var title = el("h4", null, "Compare continuations");
    var picker = el("div", "cy-walk-tabs");
    var controls = el("div", "cy-walk-nav");
    var actual = el("button", "cy-btn", "Actual game");
    var recommended = el("button", "cy-btn", "Stockfish line");
    var back = el("button", "cy-btn", "← Back");
    var forward = el("button", "cy-btn", "Forward →");
    var reset = el("button", "cy-btn", "Return to critical position");
    var caption = el("p");
    caption.setAttribute("aria-live", "polite");
    var board = el("div", "cy-continuation-board");
    var line = null, branch = "actual", offset = 0;
    function paint() {
      var steps = line[branch];
      var point = offset ? steps[offset - 1] : null;
      board.dataset.fen = point ? point.fen : line.start_fen;
      board.dataset.branch = branch;
      board.dataset.offset = String(offset);
      var label = branch === "actual" ? "Actual game" : "Hypothetical Stockfish line";
      caption.textContent = label + " · " + (point ? "Step " + offset + " · " + point.san :
        "Before critical ply " + line.ply);
      back.disabled = offset === 0;
      forward.disabled = offset === steps.length;
      recommended.disabled = !line.recommended.length;
      actual.setAttribute("aria-pressed", String(branch === "actual"));
      recommended.setAttribute("aria-pressed", String(branch === "recommended"));
      renderBoard(board, {fen: board.dataset.fen, orientation: timeline.perspective,
        coordinates: true, size: 48, pixelWidth: 360});
    }
    timeline.continuations.forEach(function (candidate) {
      var button = el("button", "cy-btn", "Critical ply " + candidate.ply);
      button.type = "button";
      button.addEventListener("click", function () {
        line = candidate;
        branch = "actual";
        offset = 0;
        navigate(line.ply - 1);
        controls.hidden = false;
        paint();
      });
      picker.append(button);
    });
    [actual, recommended, back, forward, reset].forEach(function (button) {
      button.type = "button";
    });
    actual.addEventListener("click", function () { branch = "actual"; offset = 0; paint(); });
    recommended.addEventListener("click", function () {
      branch = "recommended"; offset = 0; paint();
    });
    back.addEventListener("click", function () { offset--; paint(); });
    forward.addEventListener("click", function () { offset++; paint(); });
    reset.addEventListener("click", function () {
      navigate(line.ply - 1); offset = 0; paint();
    });
    controls.append(actual, recommended, back, forward, reset);
    controls.hidden = true;
    panel.append(title, picker, controls, caption, board);
    return panel;
  }

  function initExercises(timeline) {
    var panel = el("div", "cy-exercises");
    if (!timeline.exercises.length) return panel;
    var title = el("h4", null, "Practice from this game");
    var picker = el("div", "cy-walk-tabs");
    var board = el("div", "cy-exercise-board");
    var controls = el("div", "cy-walk-nav");
    var select = el("select", "cy-btn");
    select.setAttribute("aria-label", "Choose a legal move");
    var attempt = el("button", "cy-btn", "Try move");
    var reveal = el("button", "cy-btn", "Reveal saved lines");
    var feedback = el("p", "cy-exercise-feedback");
    feedback.setAttribute("aria-live", "polite");
    var solutionList = el("ul", "cy-exercise-solutions");
    var exercise;
    timeline.exercises.forEach(function (item) {
      var button = el("button", "cy-btn", "Practice ply " + item.ply);
      button.type = "button";
      button.addEventListener("click", function () {
        exercise = item;
        solutionList.replaceChildren();
        select.replaceChildren();
        var placeholder = el("option", null, "Choose a legal move");
        placeholder.disabled = placeholder.selected = true;
        placeholder.value = "";
        select.append(placeholder);
        for (var move of item.legal_moves) {
          var option = el("option", null, move.san);
          option.value = move.uci;
          select.append(option);
        }
        feedback.textContent = "Find a move for " + item.perspective + ".";
        controls.hidden = false;
        renderBoard(board, {fen: item.start_fen, orientation: item.perspective,
          coordinates: true, size: 48, pixelWidth: 360});
      });
      picker.append(button);
    });
    attempt.type = reveal.type = "button";
    attempt.addEventListener("click", function () {
      if (!select.value) {
        feedback.textContent = "Choose a legal move first.";
        return;
      }
      var confirmed = exercise.solutions.find(function (entry) {
        return entry.moves[0].uci === select.value;
      });
      feedback.textContent = confirmed ? "Confirmed by the saved analysis or immediate checkmate." :
        "Legal move. Its strength as a solution is unconfirmed in this report.";
    });
    reveal.addEventListener("click", function () {
      solutionList.replaceChildren();
      for (var solution of exercise.solutions) {
        var label = solution.evidence === "immediate_checkmate" ? "Also checkmates" :
          "Stockfish preferred";
        solutionList.append(el("li", null, label + " · " + solution.moves.map(function (m) {
          return m.san;
        }).join(" ")));
      }
    });
    controls.append(select, attempt, reveal);
    controls.hidden = true;
    panel.append(title, picker, board, controls, feedback, solutionList);
    return panel;
  }

  function initTimeline(root, timeline) {
    var positions = timeline.positions;
    var selected = 0;
    var graph = el("div", "cy-timeline-chart");
    var mates = el("div", "cy-timeline-mates");
    var nav = el("div", "cy-walk-nav");
    var prev = el("button", "cy-btn", "← Previous ply");
    var next = el("button", "cy-btn", "Next ply →");
    var status = el("p", null);
    status.setAttribute("aria-live", "polite");
    var positionWrap = el("div", "cy-timeline-position");
    var bar = el("div", "cy-eval-bar");
    var fill = el("span");
    var board = el("div", "cy-walk-board");
    bar.setAttribute("role", "img");
    bar.appendChild(fill);
    positionWrap.append(bar, board);
    nav.append(prev, next);
    root.append(el("h3", null, "Evaluation timeline · " + timeline.perspective + " perspective"),
      el("p", "muted", "Select a graph point or step through the game. Red marks mistakes and blunders. Diamonds mark critical plies."),
      graph, mates, nav, status, positionWrap, initContinuations(timeline, show),
      initExercises(timeline));

    function show(index) {
      selected = index;
      var point = positions[index];
      var score = point.evaluation;
      var label = point.label || "Not evaluated";
      var move = point.san ? point.move_number + " " + point.san : "Starting position";
      status.textContent = move + " · ply " + point.ply + " · " + label +
        (point.critical ? " · critical" : "") + (point.quality ? " · " + point.quality : "");
      prev.disabled = index === 0;
      next.disabled = index === positions.length - 1;
      var share = 50;
      if (score && score.kind === "cp") share += 45 * Math.tanh(score.value / 400);
      if (score && score.kind === "mate" && score.mate_for_player !== null) {
        share = score.mate_for_player ? 100 : 0;
      }
      fill.style.height = (timeline.perspective === "white" ? share : 100 - share) + "%";
      bar.style.visibility = score ? "visible" : "hidden";
      bar.setAttribute("aria-label", timeline.perspective + " evaluation " + label);
      board.setAttribute("data-ply", String(point.ply));
      board.setAttribute("data-fen", point.fen);
      renderBoard(board, { fen: point.fen, orientation: timeline.perspective,
        coordinates: true, size: 48, pixelWidth: 360 });
    }

    prev.type = next.type = "button";
    prev.addEventListener("click", function () { show(selected - 1); });
    next.addEventListener("click", function () { show(selected + 1); });
    var cp = positions.map(function (p) {
      return p.evaluation && p.evaluation.kind === "cp" ? p.evaluation.value / 100 : null;
    });
    positions.forEach(function (point, index) {
      if (!point.evaluation || point.evaluation.kind !== "mate") return;
      if (!mates.children.length) mates.append(el("strong", null, "Mate scores"));
      var label = "Ply " + point.ply + " " + point.label;
      if (point.critical) label += " · critical";
      if (point.quality === "mistake" || point.quality === "blunder") {
        label += " · " + point.quality;
      }
      var button = el("button", "cy-btn", label);
      button.type = "button";
      button.addEventListener("click", function () { show(index); });
      mates.append(button);
    });

    var details = root.closest("details");
    var plotted = false;
    function plot() {
      if (plotted || (details && !details.open) || !global.Plotly) return;
      if (!cp.some(function (value) { return value !== null; })) {
        graph.hidden = true;
        return;
      }
      plotted = true;
      global.Plotly.newPlot(graph, [{
        x: positions.map(function (point) { return point.ply; }),
        y: cp,
        mode: "lines+markers",
        customdata: positions.map(function (_, index) { return index; }),
        hovertemplate: "Ply %{x} · %{y:+.2f} pawns<extra></extra>",
        line: { color: "#1f4e79" },
        marker: {
          size: positions.map(function (p) { return p.critical ? 11 : 7; }),
          symbol: positions.map(function (p) { return p.critical ? "diamond" : "circle"; }),
          color: positions.map(function (p) {
            return p.quality === "mistake" || p.quality === "blunder" ? "#b00020" : "#1f4e79";
          }),
        },
      }], {
        height: 280, margin: { l: 60, r: 22, t: 12, b: 46 },
        xaxis: { title: { text: "PGN ply" }, rangemode: "tozero" },
        yaxis: { title: { text: "Evaluation (pawns)" } },
      }, { displayModeBar: false, responsive: true }).then(function () {
        graph.on("plotly_click", function (event) { show(event.points[0].customdata); });
      });
    }
    if (details) details.addEventListener("toggle", plot);
    plot();
    show(0);
  }

  function boot(payload) {
    var walk = document.getElementById("cy-walkthrough");
    var heat = document.getElementById("cy-heatmap");
    if (walk) initWalkthrough(walk, payload);
    if (heat) initHeatmap(heat, payload);
    var timelines = new Map((payload.timelines || []).map(function (row) {
      return [row.game_id, row];
    }));
    document.querySelectorAll("[data-cy-timeline]").forEach(function (root) {
      var timeline = timelines.get(root.getAttribute("data-cy-timeline"));
      if (timeline) initTimeline(root, timeline);
    });
    initInlineBoards(document);
  }

  global.CheckYourselfBoards = {
    renderBoard: renderBoard,
    initWalkthrough: initWalkthrough,
    initHeatmap: initHeatmap,
    initInlineBoards: initInlineBoards,
    boot: boot,
  };
})(window);
