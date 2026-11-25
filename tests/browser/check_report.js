/* Runs in a synthetic report loaded in a real, network-blocked Chrome. */
(function () {
  var tries = 0;
  function assert(condition, text) {
    if (!condition) throw new Error(text);
  }
  function check() {
    var timeline = document.querySelector(".cy-timeline");
    var graph = timeline.querySelector(".cy-timeline-chart");
    if (!graph._fullLayout || !graph.emit) {
      if (++tries < 50) return setTimeout(check, 100);
      document.body.dataset.browserCheck = "FAIL: graph did not initialize";
      return;
    }
    try {
      var board = timeline.querySelector(".cy-walk-board");
      assert(board.dataset.ply === "0", "starts at original position");
      timeline.querySelectorAll(".cy-walk-nav button")[1].click();
      assert(board.dataset.ply === "1", "next navigates to ply one");
      assert(board.dataset.fen.startsWith("rnbqkbnr/pppppppp"), "actual FEN is on board");
      assert(board.querySelectorAll("svg text").length === 16, "board coordinates");
      assert(graph.data[0].y[4] === null, "terminal mate excluded from numeric trace");
      graph.emit("plotly_click", {points: [{customdata: 2}]});
      assert(board.dataset.ply === "2", "graph event navigates to exact ply");
      var mate = [...timeline.querySelectorAll(".cy-timeline-mates button")]
        .find(function (button) { return button.textContent.includes("Ply 4"); });
      mate.click();
      assert(board.dataset.ply === "4", "mate event navigates to terminal position");
      assert(timeline.querySelector(".cy-eval-bar").ariaLabel.includes("-M0"), "mate bar label");
      var continuation = timeline.querySelector(".cy-continuation");
      continuation.querySelector(".cy-walk-tabs button").click();
      var branchBoard = continuation.querySelector(".cy-continuation-board");
      var origin = branchBoard.dataset.fen;
      var controls = continuation.querySelectorAll(".cy-walk-nav button");
      controls[3].click();
      assert(branchBoard.dataset.branch === "actual" && origin !== branchBoard.dataset.fen,
        "actual branch moves forward");
      controls[2].click();
      assert(branchBoard.dataset.fen === origin, "step back to origin");
      controls[1].click();
      controls[3].click();
      assert(branchBoard.dataset.branch === "recommended" && origin !== branchBoard.dataset.fen,
        "hypothetical branch moves forward");
      controls[4].click();
      assert(branchBoard.dataset.fen === origin, "reset to origin");

      var exercise = timeline.querySelector(".cy-exercises");
      exercise.querySelector(".cy-walk-tabs button").click();
      var quiz = exercise.querySelector(".cy-exercise-solutions");
      var select = exercise.querySelector("select");
      var buttons = exercise.querySelectorAll(".cy-walk-nav button");
      assert(!quiz.children.length, "solution hidden");
      select.selectedIndex = 1;
      buttons[0].click();
      var feedback = exercise.querySelector(".cy-exercise-feedback");
      assert(!feedback.textContent.includes("Choose"), "attempt processed");
      buttons[1].click();
      assert(quiz.children.length > 0 && quiz.textContent.includes("Stockfish preferred"),
        "solution revealed");
      if (document.querySelectorAll(".cy-timeline").length > 1) {
        assert(document.body.textContent.includes("Patterns across games"), "batch patterns");
        var last = [...document.querySelectorAll(".cy-timeline")].at(-1);
        var lastExercise = last.querySelector(".cy-exercises");
        assert(lastExercise.querySelector(".cy-walk-tabs button"), "mate exercise available");
        {
          lastExercise.closest("details").open = true;
          lastExercise.querySelector(".cy-walk-tabs button").click();
          var alternative = [...lastExercise.querySelectorAll("option")]
            .find(function (option) { return option.textContent === "Qf8#"; });
          lastExercise.querySelector("select").value = alternative.value;
          lastExercise.querySelector(".cy-walk-nav button").click();
          assert(lastExercise.textContent.includes("Confirmed"), "alternate mate accepted");
          var unverified = [...lastExercise.querySelectorAll("option")]
            .find(function (option) { return option.textContent === "Qg8+"; });
          lastExercise.querySelector("select").value = unverified.value;
          lastExercise.querySelector(".cy-walk-nav button").click();
          assert(lastExercise.textContent.includes("unconfirmed"), "other legal move is ungraded");
        }
      }
      document.body.dataset.browserCheck = "PASS";
    } catch (error) {
      document.body.dataset.browserCheck = "FAIL: " + error.message;
    }
  }
  setTimeout(check, 100);
})();
