"""Measure S2P-Joystick-Macro playback timing through S2P's real merge path.

    <S2P-XInput-Lite>\\runtime\\python.exe scripts\\measure_playback_timing.py
    python scripts\\measure_playback_timing.py --rates 133 --presses 50 --steps 200

What runs (the same pieces as tests/test_s2p_integration.py):

* This process plays S2P: a real ``ExtensionManager`` from S2P-XInput-Lite's
  ``src/extension_bridge.py`` on a private pipe, and a report thread that
  stands in for the physical controller.  At a fixed report rate it builds a
  neutral report, calls ``hub.merge_into(report)`` exactly where
  ``XInputController`` calls it before ``pad.update()``, and keeps the
  merged buttons with a ``perf_counter`` time stamp.
* A child process plays the tool: the real SDK client (``s2p_ext``) and the
  real ``MacroPlayer`` from ``macro/s2p_macro/engine.py``.  It notes when each
  step was planned to start and when it was sent.  ``perf_counter`` is
  QueryPerformanceCounter, so both processes share one clock.

Results:

1. Short presses: presses of each length separated by neutral gaps.  A
   press is a "hit" when at least one merged report contains it.  The time
   it stays on the virtual pad (until the report after its last report) is
   then sampled by simulated games that read the pad once per frame at 30,
   60 and 144 FPS with a random phase.
2. Timing error: a long macro whose every step changes the buttons.  The
   error is the time from the planned step start to the first merged report
   that shows the step, split into the player's send delay and S2P's path.

S2P's Gamepad Tester telemetry is not used for sampling: it is published at
most 360 times a second, below the 500 Hz report rate measured here.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT / "sdk", ROOT / "macro"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

BUTTON_BITS = {"A": 0x1000, "B": 0x2000, "X": 0x4000, "Y": 0x8000}
TOKEN = "timing-token"
DEFAULT_LENGTHS = (5, 10, 14, 16, 20, 25, 30, 33, 40, 45, 50, 66)
DEFAULT_FPS = (30, 60, 144)


def s2p_source():
    configured = os.environ.get("S2P_XINPUT_LITE_SRC")
    candidates = [Path(configured)] if configured else []
    candidates.append(ROOT.parent / "S2P-XInput-Lite" / "src")
    for candidate in candidates:
        if (candidate / "extension_bridge.py").is_file():
            return candidate
    raise SystemExit("S2P-XInput-Lite src not found; set S2P_XINPUT_LITE_SRC")


# ---------------------------------------------------------------------------
# Tool side (child process): real SDK client + real MacroPlayer
# ---------------------------------------------------------------------------

def run_player(pipe, plan_path, result_path):
    from s2p_ext import ExtensionClient
    from s2p_macro.engine import MacroPlayer
    from s2p_macro.model import Step

    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    steps = [Step(duration, tuple(buttons)) for duration, buttons in plan]
    client = ExtensionClient("S2P-Joystick-Macro", "timing", pipe_name=pipe, token=TOKEN)
    client.connect()
    sends = [None] * len(steps)
    current = [0]
    base = []

    def clock():
        now = time.perf_counter()
        if not base:
            base.append(now)  # MacroPlayer's first clock read starts the schedule
        return now

    def on_progress(loop, index):
        current[0] = index

    def send(step, sticks):
        index = current[0]
        if sends[index] is None:
            sends[index] = time.perf_counter()
        client.send_state(step.buttons, lt=step.lt, rt=step.rt)

    done = threading.Event()
    outcome = {}
    planned_seconds = sum(duration for duration, _buttons in plan) / 1000.0

    def on_finished(completed, error):
        outcome.update(completed=completed, error=None if error is None else repr(error))
        done.set()

    player = MacroPlayer(send, client.release_all, clock=clock)
    player.play(steps, on_progress=on_progress, on_finished=on_finished)
    if not done.wait(planned_seconds + 20.0):
        player.stop()
        outcome.update(error="playback did not finish in time")
    client.close()
    Path(result_path).write_text(json.dumps({"base": base[0], "sends": sends, **outcome}),
                                 encoding="utf-8")


# ---------------------------------------------------------------------------
# S2P side (this process): real ExtensionManager + simulated report thread
# ---------------------------------------------------------------------------

class ReportLoop(threading.Thread):
    """Physical controller stand-in: one merged report every 1/rate s."""

    def __init__(self, hub, rate_hz):
        super().__init__(name="report-loop", daemon=True)
        self.hub = hub
        self.period = 1.0 / rate_hz
        self.reports = []      # (time, merged wButtons)
        self.lateness = []     # time the report came after its schedule
        self.restarts = 0      # times the schedule restarted after a stall
        self._done = threading.Event()

    def run(self):
        reports, lateness, hub = self.reports, self.lateness, self.hub
        due = time.perf_counter()
        while not self._done.is_set():
            due += self.period
            wait = due - time.perf_counter()
            if wait > 0:
                time.sleep(wait)  # Python 3.11+: high resolution timer on Windows
            report = SimpleNamespace(wButtons=0, bLeftTrigger=0, bRightTrigger=0,
                                     sThumbLX=0, sThumbLY=0, sThumbRX=0, sThumbRY=0)
            hub.merge_into(report)
            now = time.perf_counter()  # pad.update() would run now
            reports.append((now, report.wButtons))
            lateness.append(now - due)
            if now - due > self.period:
                # More than a report behind: a real controller does not send
                # the missed reports in a burst, so restart the schedule here.
                due = now
                self.restarts += 1

    def stop(self):
        self._done.set()
        self.join(2.0)


def play_through_s2p(rate_hz, plan):
    """Play ``plan`` in a child process through a real ExtensionManager."""
    import extension_bridge as bridge
    from s2p_macro.engine import fine_timer

    pipe = rf"\\.\pipe\S2P-Extensions-timing-{uuid.uuid4().hex}"
    manager = bridge.ExtensionManager(SimpleNamespace(set_extension_input=lambda hub: None),
                                      pipe_name=pipe)
    manager.launch_tool = lambda tool_id, reopen=False, background=False: True
    manager._launch_tokens[TOKEN] = "macro"
    manager.apply(bridge.ExtensionSettings(True, (
        bridge.ToolSettings("macro", r"C:\S2P-Joystick-Macro.exe"),
    )))
    loop = ReportLoop(manager._hub, rate_hz)
    with tempfile.TemporaryDirectory() as folder, fine_timer():
        plan_path, result_path = Path(folder, "plan.json"), Path(folder, "result.json")
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        loop.start()
        planned_seconds = sum(duration for duration, _buttons in plan) / 1000.0
        try:
            subprocess.run([sys.executable, __file__, "--player", pipe, str(plan_path),
                            str(result_path)], check=True, timeout=planned_seconds + 60.0)
            time.sleep(0.1)  # let the last step reach a report
        except subprocess.TimeoutExpired:
            raise SystemExit(f"the player did not finish within {planned_seconds + 60:.0f} s")
        finally:
            loop.stop()
            manager.close()
        result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("error"):
        raise SystemExit(f"playback failed: {result['error']}")
    planned, start = [], result["base"]
    for duration, _buttons in plan:
        planned.append(start)
        start += duration / 1000.0
    return planned, result["sends"], loop


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    position = (len(ordered) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def ms_summary(seconds):
    values = [value * 1000.0 for value in seconds]
    if not values:
        nan = float("nan")
        return {"p50": nan, "p95": nan, "p99": nan, "max": nan, "min": nan, "mean": nan}
    return {
        "p50": percentile(values, 0.50), "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99), "max": max(values), "min": min(values),
        "mean": statistics.fmean(values),
    }


def visible_windows(reports, mask, held=True):
    """[start, end) times the virtual pad holds ``mask`` (or, with
    ``held=False``, does not): a run of such reports, until the next report
    replaces it."""
    windows, start = [], None
    end_marker = (None, 0 if held else mask)
    for (when, buttons), following in zip(reports, reports[1:] + [end_marker]):
        if bool(buttons & mask) == held and start is None:
            start = when
        if start is not None and bool(following[1] & mask) != held:
            end = following[0] if following[0] is not None else when
            windows.append((start, end))
            start = None
    return windows


def game_sees(window, period, phase):
    """Whether a game reading at ``phase + k * period`` reads inside window."""
    start, end = window
    first_read = phase + period * -(-(start - phase) // period)  # ceil to a read
    return first_read < end


def short_plan(order, other_ms, held):
    """Each short step (A held, or A released) between long opposite steps."""
    plan = []
    for length in order:
        if held:
            plan += [[length, ["A"]], [other_ms, []]]
        else:
            plan += [[other_ms, ["A"]], [length, []]]
    return plan


def analyse_short(lengths, order, other_ms, held, planned, sends, loop, fps, trials, rng):
    """Per length: how often the short step reached a merged report, how
    long the pad showed it, and how often simulated games read it."""
    windows = visible_windows(loop.reports, BUTTON_BITS["A"], held)
    window_index = 0
    by_length = {length: {"hits": 0, "visible": [], "presses": 0,
                          "game": {f: 0 for f in fps}} for length in lengths}
    for press, length in enumerate(order):
        step = 2 * press + (0 if held else 1)
        start = sends[step]
        limit = planned[step] + (length + other_ms) / 1000.0
        mine = []
        while window_index < len(windows) and windows[window_index][0] < limit:
            if windows[window_index][0] >= start:
                mine.append(windows[window_index])
            window_index += 1
        entry = by_length[length]
        entry["presses"] += 1
        if not mine:
            entry["visible"].append(0.0)
            continue
        entry["hits"] += 1
        entry["visible"].append(sum(end - begin for begin, end in mine))
        for f in fps:
            period = 1.0 / f
            for _ in range(trials):
                phase = rng.random() * period
                if any(game_sees(window, period, phase) for window in mine):
                    entry["game"][f] += 1
    rows = []
    for length in lengths:
        entry = by_length[length]
        visible_ms = [value * 1000.0 for value in entry["visible"]]
        rows.append({
            "length_ms": length,
            "presses": entry["presses"],
            "output_hits": entry["hits"],
            "visible_ms_min": min(visible_ms),
            "visible_ms_p50": percentile(visible_ms, 0.5),
            "game_hit_rate": {str(f): entry["game"][f] / (entry["presses"] * trials) for f in fps},
        })
    return rows


def analyse_steps(plan, planned, sends, loop):
    reports = loop.reports
    pointer, appear = 0, []
    for (duration, buttons), send in zip(plan, sends):
        mask = sum(BUTTON_BITS[name] for name in buttons)
        while pointer < len(reports) and (reports[pointer][0] < send or reports[pointer][1] != mask):
            pointer += 1
        appear.append(reports[pointer][0] if pointer < len(reports) else None)
    found = [index for index, when in enumerate(appear) if when is not None]
    held = [
        (appear[index + 1] - appear[index]) - plan[index][0] / 1000.0
        for index in found if index + 1 < len(appear) and appear[index + 1] is not None
    ]
    return {
        "steps": len(plan),
        "missed": len(plan) - len(found),
        "total_error_ms": ms_summary([appear[i] - planned[i] for i in found]),
        "send_delay_ms": ms_summary([sends[i] - planned[i] for i in found]),
        "s2p_path_ms": ms_summary([appear[i] - sends[i] for i in found]),
        "held_error_ms": ms_summary(held),
        "last_step_error_ms": (
            (appear[found[-1]] - planned[found[-1]]) * 1000.0 if found else float("nan")
        ),
    }


def needed_length(rows, f):
    """Shortest tested length from which every longer one is always seen."""
    answer = None
    for row in reversed(rows):
        if row["game_hit_rate"][str(f)] < 1.0:
            break
        answer = row["length_ms"]
    return answer


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def measure(rate_hz, args, rng):
    print(f"\n=== {rate_hz} Hz reports ===", flush=True)
    order = [length for length in args.lengths for _ in range(args.presses)]
    rng.shuffle(order)
    print(f"short presses: {len(order)} presses ...", flush=True)
    planned, sends, loop = play_through_s2p(rate_hz, short_plan(order, args.gap, True))
    presses = analyse_short(args.lengths, order, args.gap, True, planned, sends, loop,
                            args.fps, args.trials, rng)
    lateness = ms_summary(loop.lateness)
    restarts = loop.restarts
    releases = None
    if not args.no_releases:
        rng.shuffle(order)
        print(f"short releases: {len(order)} releases ...", flush=True)
        planned, sends, loop = play_through_s2p(rate_hz, short_plan(order, args.gap, False))
        releases = analyse_short(args.lengths, order, args.gap, False, planned, sends, loop,
                                 args.fps, args.trials, rng)
        restarts += loop.restarts

    cycle = ["A", "B", "X", "Y"]
    step_plan = [[rng.randint(args.min_step, args.max_step), [cycle[index % 4]]]
                 for index in range(args.steps)]
    print(f"timing: {len(step_plan)} steps ...", flush=True)
    planned, sends, loop = play_through_s2p(rate_hz, step_plan)
    timing = analyse_steps(step_plan, planned, sends, loop)
    restarts += loop.restarts

    print("short presses (A held between neutral gaps):")
    print_presses(presses, args.fps)
    if releases is not None:
        print("short releases (A released between holds):")
        print_presses(releases, args.fps)
    print_timing(timing)
    print(f"report thread lateness ms: p50 {lateness['p50']:.2f}  p99 {lateness['p99']:.2f}"
          f"  max {lateness['max']:.2f}  schedule restarts after a stall: {restarts}")
    needed = {"presses": {str(f): needed_length(presses, f) for f in args.fps}}
    if releases is not None:
        needed["releases"] = {str(f): needed_length(releases, f) for f in args.fps}
    return {"rate_hz": rate_hz, "presses": presses, "releases": releases, "timing": timing,
            "report_lateness_ms": lateness, "report_restarts": restarts, "needed_ms": needed}


def print_presses(rows, fps):
    head = "  len ms  output hits  visible min/p50 ms  " + "  ".join(f"{f:>3} FPS" for f in fps)
    print(head)
    for row in rows:
        games = "  ".join(f"{row['game_hit_rate'][str(f)] * 100:6.1f}%" for f in fps)
        print(f"  {row['length_ms']:6}  {row['output_hits']:5}/{row['presses']:<5}"
              f"  {row['visible_ms_min']:7.2f} / {row['visible_ms_p50']:6.2f}   {games}")


def print_timing(timing):
    print(f"  steps {timing['steps']}, missed {timing['missed']}")
    for key in ("total_error_ms", "send_delay_ms", "s2p_path_ms", "held_error_ms"):
        s = timing[key]
        print(f"  {key:15} p50 {s['p50']:6.2f}  p95 {s['p95']:6.2f}  p99 {s['p99']:6.2f}"
              f"  max {s['max']:6.2f}")
    print(f"  last step error {timing['last_step_error_ms']:.2f} ms")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rates", type=float, nargs="+", default=[133, 500],
                        help="physical report rates in Hz (default: 133 500)")
    parser.add_argument("--lengths", type=int, nargs="+", default=list(DEFAULT_LENGTHS),
                        help="press lengths in ms")
    parser.add_argument("--presses", type=int, default=200, help="presses per length")
    parser.add_argument("--gap", type=int, default=50, help="neutral gap after each press, ms")
    parser.add_argument("--fps", type=int, nargs="+", default=list(DEFAULT_FPS))
    parser.add_argument("--trials", type=int, default=50,
                        help="random game phases sampled per press")
    parser.add_argument("--steps", type=int, default=1000, help="steps in the timing macro")
    parser.add_argument("--min-step", type=int, default=20)
    parser.add_argument("--max-step", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--json", type=Path, help="also write the results to this file")
    parser.add_argument("--no-releases", action="store_true",
                        help="skip the short release measurement")
    parser.add_argument("--player", nargs=3, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.player:
        run_player(*args.player)
        return
    if sys.platform != "win32":
        raise SystemExit("needs Windows (named pipes)")
    source = s2p_source()
    sys.path.insert(0, str(source))
    args.lengths = sorted(set(args.lengths))
    rng = random.Random(args.seed)
    results = {
        "conditions": {
            "python": sys.version.split()[0], "platform": platform.platform(),
            "processor": platform.processor(), "cpus": os.cpu_count(),
            "s2p_source": str(source), "presses_per_length": args.presses,
            "gap_ms": args.gap, "trials": args.trials, "steps": args.steps,
            "step_ms": [args.min_step, args.max_step], "seed": args.seed,
        },
        "rates": [measure(rate, args, rng) for rate in args.rates],
    }
    print("\nshortest tested step always seen by the game:")
    for entry in results["rates"]:
        for kind, needed in entry["needed_ms"].items():
            text = ", ".join(f"{f} FPS: {needed[str(f)]} ms" for f in args.fps)
            print(f"  {entry['rate_hz']:g} Hz reports, {kind:8} -> {text}")
    if args.json:
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
