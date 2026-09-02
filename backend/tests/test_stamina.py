# -*- coding: utf-8 -*-
"""Sprint stamina.

The module is plain JavaScript with no DOM in it, so it can be run for
real rather than just read. Node is not a dependency of this project, so
these skip rather than fail where it is missing — the constant checks
below run everywhere and catch the mistakes that matter most.
"""

import json
import os
import re
import shutil
import subprocess
import textwrap

import pytest

GAME_JS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static", "js", "game",
)

node = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def constant(name):
    with open(os.path.join(GAME_JS, "config.js"), encoding="utf-8") as handle:
        source = handle.read()
    match = re.search(rf"export const {name} = ([0-9.]+);", source)
    assert match, f"{name} is not exported"
    return float(match.group(1))


def run(body):
    """Run a snippet against the real stamina module and read back JSON."""
    script = textwrap.dedent(f"""
        import {{ getStamina, resetStamina, stepStamina }} from "./stamina.js";
        const out = (v) => console.log(JSON.stringify(v));
        {body}
    """)
    path = os.path.join(GAME_JS, "_stamina_probe.mjs")
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(script)
        result = subprocess.run(
            ["node", path], capture_output=True, text=True, timeout=30, check=True,
        )
    finally:
        if os.path.exists(path):
            os.remove(path)

    return [json.loads(line) for line in result.stdout.strip().splitlines()]


# ---------------------------------------------------------------------------
# The numbers
# ---------------------------------------------------------------------------

def test_recovering_is_slower_than_spending():
    """Otherwise sprinting is free and the bar is decoration."""
    assert constant("RECOVER_SECONDS") > constant("SPRINT_SECONDS")


def test_running_dry_locks_sprint_off_for_a_meaningful_while():
    cleared = constant("EXHAUSTED_CLEARS_AT")
    assert 0 < cleared < 1, "an empty bar has to stay empty for a bit"
    assert cleared >= 0.2, "clearing this low is barely a penalty"


def test_recovery_does_not_start_the_instant_you_let_go():
    assert constant("RECOVERY_DELAY_SECONDS") > 0


# ---------------------------------------------------------------------------
# The behaviour
# ---------------------------------------------------------------------------

@node
def test_a_full_bar_buys_about_the_advertised_sprint():
    budget = constant("SPRINT_SECONDS")
    [held] = run("""
        resetStamina();
        let t = 0;
        while (stepStamina(1 / 60, true)) t += 1 / 60;
        out(t);
    """)
    assert budget - 0.1 <= held <= budget + 0.1


@node
def test_sprint_stays_locked_off_until_the_bar_has_come_back():
    """Tapping the button must not buy a permanent speed boost."""
    [samples] = run("""
        resetStamina();
        while (stepStamina(1 / 60, true)) { /* burn it all */ }
        // Now hammer the button while it recovers.
        const got = [];
        for (let i = 0; i < 60 * 12; i++) got.push(stepStamina(1 / 60, true));
        out({ any: got.some(Boolean), first: got.indexOf(true) });
    """)
    assert samples["any"], "sprint never came back at all"
    # It has to stay off for a good stretch, not flicker back immediately.
    assert samples["first"] / 60 > 1.0


@node
def test_standing_still_refills_the_bar():
    [level] = run("""
        resetStamina();
        for (let i = 0; i < 60 * 2; i++) stepStamina(1 / 60, true);
        for (let i = 0; i < 60 * 30; i++) stepStamina(1 / 60, false);
        out(getStamina().level);
    """)
    assert level == pytest.approx(1.0, abs=1e-6)


@node
def test_the_bar_never_leaves_its_range():
    [bounds] = run("""
        resetStamina();
        let lo = 1, hi = 0;
        for (let i = 0; i < 60 * 60; i++) {
            stepStamina(1 / 60, i % 100 < 70);
            const { level } = getStamina();
            lo = Math.min(lo, level); hi = Math.max(hi, level);
        }
        out({ lo, hi });
    """)
    assert bounds["lo"] >= 0 and bounds["hi"] <= 1


@node
def test_the_drain_does_not_depend_on_the_frame_rate():
    """A 144Hz phone must not get more sprint than a 30Hz laptop."""
    [fast, slow] = run("""
        for (const step of [1 / 144, 1 / 30]) {
            resetStamina();
            let t = 0;
            while (stepStamina(step, true)) t += step;
            out(t);
        }
    """)
    assert abs(fast - slow) < 0.1


@node
def test_a_new_round_hands_everybody_a_full_bar():
    [level] = run("""
        resetStamina();
        for (let i = 0; i < 60 * 3; i++) stepStamina(1 / 60, true);
        resetStamina();
        out(getStamina().level);
    """)
    assert level == 1
