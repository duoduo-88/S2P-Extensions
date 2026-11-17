import threading
import time
import unittest

import _paths  # noqa: F401

from s2p_macro import engine
from s2p_macro.engine import MacroPlayer, MacroRecorder, state_from_input
from s2p_macro.model import Step


class FakeS2P:
    def __init__(self):
        self.sent = []
        self.releases = 0
        self.lock = threading.Lock()
        self.fail_after = None

    def send(self, step, sticks):
        with self.lock:
            if self.fail_after is not None and len(self.sent) >= self.fail_after:
                raise ConnectionError("S2P closed")
            self.sent.append((time.perf_counter(), step, frozenset(sticks)))

    def release(self):
        with self.lock:
            self.releases += 1


def wait_done(player, timeout=5.0):
    deadline = time.monotonic() + timeout
    while player.running and time.monotonic() < deadline:
        time.sleep(0.005)
    return not player.running


class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.s2p = FakeS2P()
        self.player = MacroPlayer(self.s2p.send, self.s2p.release)
        self.addCleanup(self.player.stop)

    def test_steps_follow_the_schedule_and_end_released(self):
        steps = [Step(40, ("A",)), Step(40, ("B",)), Step(40)]
        finished = []
        started = time.perf_counter()
        self.player.play(steps, on_finished=lambda done, error: finished.append((done, error)))
        self.assertTrue(wait_done(self.player))
        elapsed = time.perf_counter() - started
        self.assertEqual([item[1] for item in self.s2p.sent], steps)
        offsets = [item[0] - self.s2p.sent[0][0] for item in self.s2p.sent]
        self.assertAlmostEqual(offsets[1], 0.040, delta=0.015)
        self.assertAlmostEqual(offsets[2], 0.080, delta=0.015)
        self.assertGreaterEqual(elapsed, 0.115)
        self.assertEqual(self.s2p.releases, 1)
        self.assertEqual(finished, [(1, None)])

    def test_long_holds_send_heartbeats(self):
        self.player.play([Step(700, ("A",))])
        self.assertTrue(wait_done(self.player))
        # Initial send plus a resend every 250 ms keeps S2P's 1 s timeout away.
        self.assertGreaterEqual(len(self.s2p.sent), 3)
        gaps = [b[0] - a[0] for a, b in zip(self.s2p.sent, self.s2p.sent[1:])]
        self.assertLess(max(gaps), engine.HEARTBEAT_SECONDS + 0.05)

    def test_loops_insert_a_release_gap_and_speed_scales(self):
        self.player.play([Step(40, ("A",))], loops=3, speed=2.0, loop_gap_ms=20)
        self.assertTrue(wait_done(self.player))
        buttons = [item[1].buttons for item in self.s2p.sent]
        self.assertEqual(buttons, [("A",), (), ("A",), (), ("A",)])

    def test_stop_releases_immediately(self):
        finished = []
        self.player.play([Step(5000, ("X",))], loops=0,
                         on_finished=lambda done, error: finished.append(done))
        time.sleep(0.05)
        started = time.perf_counter()
        self.player.stop()
        self.assertLess(time.perf_counter() - started, 0.2)
        self.assertEqual(self.s2p.releases, 1)
        self.assertEqual(finished, [0])

    def test_lost_connection_ends_playback_and_reports_it(self):
        self.s2p.fail_after = 1
        finished = []
        self.player.play([Step(20, ("A",)), Step(20, ("B",))],
                         on_finished=lambda done, error: finished.append(error))
        self.assertTrue(wait_done(self.player))
        self.assertIsInstance(finished[0], ConnectionError)
        self.assertEqual(self.s2p.releases, 1)

    def test_sticks_are_passed_through(self):
        self.player.play([Step(10, left=(5, 5))], sticks={"left"})
        self.assertTrue(wait_done(self.player))
        self.assertEqual(self.s2p.sent[0][2], frozenset({"left"}))

    def test_invalid_requests(self):
        with self.assertRaises(ValueError):
            self.player.play([])
        with self.assertRaises(ValueError):
            self.player.play([Step(10)], speed=50)


class RecorderTests(unittest.TestCase):
    def test_records_changes_after_first_input(self):
        script = [
            {"frame": 1, "buttons": []},
            {"frame": 2, "buttons": []},
            {"frame": 3, "buttons": ["A"]},
            {"frame": 3, "buttons": ["A"]},  # same frame: ignored
            {"frame": 4, "buttons": ["A"]},
            {"frame": 5, "buttons": ["A", "B"], "rt": 255},
            {"frame": 6, "buttons": []},
        ]
        position = {"index": 0}

        def get_input():
            index = min(position["index"], len(script) - 1)
            position["index"] += 1
            return script[index]

        recorder = MacroRecorder(get_input, poll_seconds=0.01)
        recorder.start()
        deadline = time.monotonic() + 2
        while position["index"] < len(script) + 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        steps = recorder.stop()
        self.assertEqual([step.buttons for step in steps], [("A",), ("A", "B")])
        self.assertEqual(steps[1].rt, 255)
        self.assertEqual(recorder.change_count, 3)
        self.assertGreater(recorder.elapsed, 0)

    def test_connection_error_stops_recording(self):
        def get_input():
            raise ConnectionError("gone")

        recorder = MacroRecorder(get_input, poll_seconds=0.01)
        recorder.start()
        time.sleep(0.05)
        self.assertFalse(recorder.running)
        self.assertEqual(recorder.stop(), [])
        self.assertIsInstance(recorder.error, ConnectionError)

    def test_stick_recording_is_optional_and_ignores_noise(self):
        reply = {"buttons": [], "lx": 500, "ly": -300, "rx": 20000, "ry": 0}
        self.assertTrue(state_from_input(reply, record_sticks=False).is_neutral)
        state = state_from_input(reply, record_sticks=True)
        self.assertEqual((state.left, state.right), ((0, 0), (20000, 0)))



class TriggerMonitorTests(unittest.TestCase):
    def run_script(self, frames, triggers):
        """Feed frames straight into process(): deterministic, no thread timing."""
        monitor = engine.TriggerMonitor(lambda: {}, lambda name: None)
        monitor.set_triggers(triggers)
        fired = []
        for number, buttons in enumerate(frames, start=1):
            for _repeat in range(2):  # a repeated poll of the same frame is ignored
                name = monitor.process({"frame": number, "buttons": buttons})
                if name is not None:
                    fired.append(name)
        return fired

    def test_thread_reports_triggers(self):
        frames = iter([[], ["A", "B"]] + [[]] * 1000)
        fired = []
        counter = {"frame": 0}

        def get_input():
            counter["frame"] += 1
            return {"frame": counter["frame"], "buttons": next(frames)}

        monitor = engine.TriggerMonitor(get_input, fired.append, poll_seconds=0.001)
        monitor.set_triggers({"Combo": ("A", "B")})
        monitor.start()
        deadline = time.monotonic() + 2
        while not fired and time.monotonic() < deadline:
            time.sleep(0.005)
        monitor.stop()
        self.assertEqual(fired, ["Combo"])

    def test_fires_once_per_press_on_the_rising_edge(self):
        frames = [[], ["BACK"], ["BACK", "Y"], ["BACK", "Y"], ["BACK"], ["BACK", "Y"], []]
        self.assertEqual(self.run_script(frames, {"Dash": ("BACK", "Y")}), ["Dash", "Dash"])

    def test_the_largest_matching_combination_wins(self):
        frames = [[], ["BACK", "Y", "X"], []]
        fired = self.run_script(frames, {"Small": ("BACK", "Y"), "Big": ("BACK", "Y", "X")})
        self.assertEqual(fired, ["Big"])

    def test_lost_connection_stops_the_monitor(self):
        def get_input():
            raise ConnectionError("gone")

        monitor = engine.TriggerMonitor(get_input, lambda name: None, poll_seconds=0.002)
        monitor.start()
        time.sleep(0.05)
        self.assertFalse(monitor.running)
        self.assertIsInstance(monitor.error, ConnectionError)


if __name__ == "__main__":
    unittest.main()
