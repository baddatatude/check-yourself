"""ACPL capping tests."""

from __future__ import annotations

from check_yourself.engine.evaluation import ACPL_LOSS_CAP_CP, capped_eval_loss_for_acpl


def test_capped_eval_loss_for_acpl() -> None:
    assert capped_eval_loss_for_acpl(50) == 50
    assert capped_eval_loss_for_acpl(ACPL_LOSS_CAP_CP) == ACPL_LOSS_CAP_CP
    assert capped_eval_loss_for_acpl(99_000) == ACPL_LOSS_CAP_CP
    assert capped_eval_loss_for_acpl(-5) == 0
