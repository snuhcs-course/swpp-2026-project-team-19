"""guard_effect.py on the dev bars (I4-P38). The I3 set is not run in tests."""

import guard_effect


def test_guard_effect_on_the_dev_bars(capsys):
    assert guard_effect.main(["dev", "service"]) == 0
    out = capsys.readouterr().out
    result = guard_effect.measure("dev", "service")
    assert result["lines"] == 836 and result["without"]["false_merge"] == result["with"]["false_merge"] == 0
    # the guard takes confirmations away and nothing else
    assert result["with"]["confirmed"] == result["without"]["confirmed"] - result["lost_confirmation"]
    assert result["with"]["confirm"] == result["without"]["confirm"] + result["lost_confirmation"]
    assert all(result["with"][k] == result["without"][k] for k in ("choose", "register", "wrong"))
    # measured 2026-11-13: 6 lines, all of them matched to the right product
    assert (result["lost_confirmation"], result["of_them_right"], result["of_them_false_merge"]) == (6, 6, 0)
    assert "lost confirmation: 6 (right product 6, false merge 0)" in out
    assert guard_effect.harness.Backend.resolve.__name__ == "resolve"
