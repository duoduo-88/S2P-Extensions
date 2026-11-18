# S2P-Joystick-Macro playback timing

[繁體中文](playback-timing_zh-TW.md) · [S2P-Extensions](../README.md) · [S2P-Joystick-Macro](../macro/README.md)

How short can a macro step be and still reach the game, and how close to
plan does playback run? This page reports a measurement through S2P's real
merge path and explains the step length guidance in the macro guides:
**keep each step at least two of the game's input reads long**. The
macro app marks shorter steps in orange, using its **Game input rate**
setting: under 66 ms at 30 Hz, 33 ms at 60 Hz, 16 ms at 144 Hz or more.
The measurement confirms these limits.

On this page **FPS** means how often the game reads the controller. That is
not always its frame rate: many games read input 60 times a second however
fast the screen runs.

## Summary

- **S2P never loses a press.** Every press, even 5 ms, reached at least one
  merged report (S2P latches a press shorter than one report). A release
  shorter than one report can disappear: at 133 Hz, 62 of 200 releases of
  5 ms never showed up.
- **The game can still miss a short step.** The virtual pad holds a step
  for its length rounded to whole reports, so up to one report period
  less. A game that reads once per frame sees the step only if the pad held
  it for a whole frame. 16 ms at 60 FPS was seen 91.9% of the time at
  133 Hz and 95.5% at 500 Hz.
- **Shortest step the game always saw:** about one game frame plus one
  report period.

  | Reports | 30 FPS | 60 FPS | 144 FPS |
  |---|---|---|---|
  | 133 Hz (ESP32 bridge) | 40 ms | 25 ms | 5 ms (press), 10 ms (release) |
  | 500 Hz | 40 ms | 20 ms | 10 ms |

  The app's limits (66 / 33 / 16 ms) are at or above every value, so the
  guidance stands.
- **Playback timing error** (planned step start to the first merged report
  that shows it, 1000 steps):

  | Reports | P50 | P95 | P99 | Max |
  |---|---|---|---|---|
  | 133 Hz | 4.90 ms | 8.59 ms | 9.28 ms | 10.10 ms |
  | 500 Hz | 2.08 ms | 3.26 ms | 3.49 ms | 4.24 ms |

  Most of it is waiting for the next report. The player itself sends each
  step within 1.9 ms (P99) of plan, and the schedule does not drift: the
  last of the 1000 steps was 1.7 ms (133 Hz) and 1.1 ms (500 Hz) late.

## How it was measured

[`scripts/measure_playback_timing.py`](../scripts/measure_playback_timing.py)
uses the same pieces as `tests/test_s2p_integration.py`; no other software
is involved.

- **S2P side (script process):** a real `ExtensionManager` from
  S2P-XInput-Lite's `src/extension_bridge.py` on a private pipe. A report
  thread stands in for the physical controller: at a fixed rate it builds a
  neutral report, calls `merge_into(report)` where `XInputController` calls
  it just before `pad.update()`, and stores the merged buttons with a time
  stamp. This is the report that S2P sends to the virtual pad and to the
  Gamepad Tester; the tester's telemetry is not sampled because it is
  published at most 360 times a second.
- **Tool side (child process):** the real SDK client (`s2p_ext`) and the
  real `MacroPlayer` from `macro/s2p_macro/engine.py`, connected through the
  pipe like the macro app. It notes each step's planned start and the time
  it was sent. Both processes use `perf_counter`
  (QueryPerformanceCounter), one system-wide clock.
- **Short steps:** for each length, 200 presses of A, each followed by a
  50 ms neutral gap, in random order. Then the same for releases: A held for
  50 ms, released for the tested length. A step counts as an output hit when
  at least one merged report shows it. Its held time runs from that report
  to the report that replaces it.
- **Simulated games:** a game reads the pad every 1/FPS s. For each step,
  50 random phases were tried per frame rate. The game sees the step when a
  read falls inside the held time.
- **Timing error:** a 1000-step macro whose steps cycle A, B, X, Y (so every
  step changes the output) with random lengths of 20–100 ms. The error is
  split into the player's send delay and S2P's path (pipe, then waiting for
  the next report).

Run it with S2P's bundled interpreter (plain Python 3.11 or later works
too); the default run takes about 16 minutes:

```powershell
..\S2P-XInput-Lite\runtime\python.exe scripts\measure_playback_timing.py --json timing.json
```

`--rates`, `--lengths`, `--presses`, `--steps` and `--no-releases` make a
shorter run, for example `--rates 133 --presses 50 --steps 200`.

## Conditions

| | |
|---|---|
| Date | 2026-11-18 |
| Machine | AMD Ryzen 7 5700X3D (8 cores, 16 threads), 64 GB, Windows 11 Pro 10.0.26300, desktop otherwise idle |
| Python | 3.11.9 (S2P-XInput-Lite `runtime\python.exe`) |
| Code | S2P-XInput-Lite `2b45aab`, S2P-Extensions `6bbe066` with the uncommitted macro changes of that day |
| Report rates | 133 Hz and 500 Hz, fixed schedule (report thread P99 lateness 0.7 ms at 133 Hz, 0.5 ms at 500 Hz) |
| Short steps | 5, 10, 14, 16, 20, 25, 30, 33, 40, 45, 50, 66 ms; 200 each; 50 ms opposite step between them |
| Games | 30, 60, 144 FPS, fixed frame period, 50 random phases per step |
| Timing macro | 1000 steps, 20–100 ms, seed 1 |

Not included: the real input thread's per-report work and the serial or
USB jitter of a real controller, the ViGEm driver and the game's own input
lag (a constant delay that does not change what the game sees), and frame
time jitter in the game. A busy PC, an irregular controller or a game with
uneven frame times needs more margin, which two reads provide.

## Results

### Short presses

Output hits are presses that reached at least one merged report; "held" is
how long the virtual pad held the press (shortest of 200). The FPS columns
are how often a simulated game read it.

**133 Hz reports**

| Press | Output hits | Held, shortest | 30 FPS | 60 FPS | 144 FPS |
|---|---|---|---|---|---|
| 5 ms | 200/200 | 7.03 ms | 22.2% | 44.0% | 100% |
| 10 ms | 200/200 | 7.02 ms | 29.5% | 61.5% | 100% |
| 14 ms | 200/200 | 7.12 ms | 43.5% | 85.8% | 100% |
| 16 ms | 200/200 | 14.50 ms | 47.5% | 91.9% | 100% |
| 20 ms | 200/200 | 14.58 ms | 59.7% | 96.7% | 100% |
| 25 ms | 200/200 | 22.09 ms | 75.7% | 100% | 100% |
| 30 ms | 200/200 | 22.48 ms | 89.6% | 100% | 100% |
| 33 ms | 200/200 | 29.37 ms | 93.7% | 100% | 100% |
| 40 ms | 200/200 | 36.85 ms | 100% | 100% | 100% |
| 45 ms | 200/200 | 37.50 ms | 100% | 100% | 100% |
| 50 ms | 200/200 | 44.35 ms | 100% | 100% | 100% |
| 66 ms | 200/200 | 59.75 ms | 100% | 100% | 100% |

**500 Hz reports**

| Press | Output hits | Held, shortest | 30 FPS | 60 FPS | 144 FPS |
|---|---|---|---|---|---|
| 5 ms | 200/200 | 3.55 ms | 14.7% | 30.2% | 70.5% |
| 10 ms | 200/200 | 7.68 ms | 29.3% | 60.2% | 100% |
| 14 ms | 200/200 | 11.57 ms | 41.2% | 84.3% | 100% |
| 16 ms | 200/200 | 13.56 ms | 47.9% | 95.5% | 100% |
| 20 ms | 200/200 | 17.81 ms | 59.7% | 100% | 100% |
| 25 ms | 200/200 | 22.09 ms | 75.1% | 100% | 100% |
| 30 ms | 200/200 | 27.94 ms | 89.9% | 100% | 100% |
| 33 ms | 200/200 | 31.55 ms | 98.2% | 100% | 100% |
| 40 ms | 200/200 | 37.91 ms | 100% | 100% | 100% |
| 45 ms | 200/200 | 43.51 ms | 100% | 100% | 100% |
| 50 ms | 200/200 | 47.55 ms | 100% | 100% | 100% |
| 66 ms | 200/200 | 63.54 ms | 100% | 100% | 100% |

At 133 Hz every press is held for at least one report (7.5 ms), longer than
a 144 FPS frame (6.9 ms), so a 144 FPS game saw all of them.

### Short releases

Releases are not latched, so a release shorter than one report can be
lost before it reaches the pad. From 10 ms on, releases matched presses
within sampling noise.

| Release | 133 Hz: output hits | 133 Hz: 60 / 144 FPS | 500 Hz: output hits | 500 Hz: 60 / 144 FPS |
|---|---|---|---|---|
| 5 ms | 138/200 | 31.1% / 69.0% | 200/200 | 29.9% / 71.1% |
| 10 ms | 200/200 | 58.8% / 100% | 200/200 | 60.3% / 100% |
| 16 ms | 200/200 | 91.5% / 100% | 200/200 | 95.4% / 100% |
| 25 ms | 200/200 | 100% / 100% | 200/200 | 100% / 100% |
| 33 ms | 200/200 | 100% / 100% | 200/200 | 100% / 100% |
| 40 ms | 200/200 | 100% / 100% | 200/200 | 100% / 100% |

At 30 FPS, releases also needed 40 ms at both rates.

### Timing error

| | 133 Hz P50 / P95 / P99 / max | 500 Hz P50 / P95 / P99 / max |
|---|---|---|
| Total: plan to merged report | 4.90 / 8.59 / 9.28 / 10.10 ms | 2.08 / 3.26 / 3.49 / 4.24 ms |
| Player: plan to send | 0.81 / 1.69 / 1.92 / 2.43 ms | 0.70 / 1.34 / 1.55 / 2.20 ms |
| S2P: send to merged report | 4.05 / 7.54 / 7.63 / 7.94 ms | 1.00 / 2.05 / 2.13 / 2.39 ms |
| Held time minus step length | −0.06 / 5.30 / 6.57 / 8.05 ms | 0.00 / 1.62 / 2.02 / 2.33 ms |

No step was missed in either run. S2P's part is close to uniform between 0
and one report period, as expected for input that waits for the next
report.

## What it means for macro steps

A step reaches the game when the pad holds it for a whole read interval.
The pad holds it for the step length give or take one report period, so
the shortest safe step is about **one read interval plus one report
period**. Two reads cover that whenever the controller reports at least as
often as the game reads, and it also held at 144 FPS on a 133 Hz bridge
(14 ms steps, presses and releases). The app's 16 ms limit for 144 Hz or
more keeps a little more margin. Shorter steps work only some of the time; use **Speed** below 1 to
stretch a fast macro instead.
