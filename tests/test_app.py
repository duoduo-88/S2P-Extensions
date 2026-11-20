"""Smoke test of the Tk window with a fake S2P connection."""

import gc
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import _paths  # noqa: F401

from s2p_macro import app as app_module
from s2p_macro.model import Macro, MacroLibrary, Step
from s2p_macro.settings import AppSettings


class FakeClient:
    connected = True

    def __init__(self, granted=("input", "read"), sticks=()):
        self.granted = set(granted)
        self.granted_sticks = set(sticks)
        self.states = []
        self.released = 0
        self.frames = []

    def send_state(self, buttons, lt=None, rt=None, left=None, right=None):
        self.states.append((tuple(buttons), left))

    def release_all(self):
        self.released += 1

    def get_input(self):
        return self.frames.pop(0) if self.frames else {"frame": 0}


class FakeConnection:
    """Mimics AutoConnection: a reconnect builds a client from the factory."""

    def __init__(self, factory, on_change, on_host_exit=None):
        self.factory = factory
        self.on_change = on_change
        self.on_host_exit = on_host_exit
        self.client = FakeClient()
        self.claims = []

    def start(self):
        self.on_change("connected", "")

    def reconnect(self):
        wanted = tuple(self.factory().sticks)
        self.claims.append(wanted)
        self.client = FakeClient(sticks=wanted)

    def stop(self):
        pass


class FakeTray:
    def __init__(self, app):
        self.visible = False
        self.actions = []
        self.stopped = False

    def start(self):
        return True

    def show(self):
        self.visible = True
        return True

    def hide(self):
        self.visible = False

    def get_action(self):
        return self.actions.pop(0) if self.actions else None

    def update_labels(self, show_label, exit_label):
        self.labels = (show_label, exit_label)

    def stop(self):
        self.stopped = True


class MacroAppTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name)
        settings = AppSettings(notice_accepted=True, language="en")
        settings.save(self.data / "settings.json")
        library = MacroLibrary(self.data / "macros")
        library.save(Macro("Buttons", [Step(30, ("A",)), Step(30, ("B",))]))
        library.save(Macro("Stick", [Step(30, ("A",)), Step(30, ("B",), left=(0, 1000))]))
        self.root = tk.Tk()
        self.root.withdraw()
        self.stopped_connections = []
        self.app = app_module.MacroApp(
            self.root, data_dir=self.data, connection_factory=FakeConnection, tray_factory=FakeTray,
        )
        self.addCleanup(self._close)

    def _close(self):
        try:
            if self.root.winfo_exists():
                self.app.close()
        except tk.TclError:
            pass
        # Free this window's Tk objects now, on the main thread.  Left to the
        # garbage collector they may be freed later on a worker thread of
        # another test, where Tk raises "main thread is not in main loop".
        self.app = self.root = None
        gc.collect()

    def pump(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)

    def select(self, name):
        names = self.app.macro_list.get(0, "end")
        self.app.macro_list.selection_clear(0, "end")
        self.app.macro_list.selection_set(names.index(name))
        self.app.select_macro()

    def test_title_is_not_translated_and_has_a_v_version(self):
        self.assertEqual(self.root.title(), f"S2P-Joystick-Macro v{app_module.__version__}")
        self.app.toggle_language()
        self.assertEqual(self.root.title(), f"S2P-Joystick-Macro v{app_module.__version__}")
        self.assertEqual(self.app.record_button.cget("text"), "錄製")
        self.assertEqual(AppSettings.load(self.data / "settings.json").language, "zh")

    def test_lists_macros_and_shows_steps(self):
        self.assertEqual(self.app.macro_list.get(0, "end"), ("Buttons", "Stick"))
        self.select("Stick")
        self.assertEqual(len(self.app.step_tree.get_children()), 2)
        self.assertEqual(self.app.step_tree.set("0", "buttons"), "A")
        self.assertIn("2 steps", self.app.summary_label.cget("text"))
        self.pump(0.2)
        self.assertIn("Connected to S2P (input / read)", self.app.connection_label.cget("text"))

    def test_steps_a_game_may_miss_are_marked(self):
        tree = self.app.step_tree
        self.app.refresh_steps(steps=[Step(20, ("A",)), Step(33, ("A", "B")), Step(32, ())])
        self.assertEqual([tree.item(item, "tags") for item in tree.get_children()],
                         [("short",), "", ("short",)])
        self.assertEqual(tree.set("1", "buttons"), "A + B")
        self.assertEqual(self.app.short_label.cget("text"), "2 in orange: under 33 ms as played")
        self.app.refresh_steps(steps=[Step(40, ("A",))])
        self.assertEqual(self.app.short_label.cget("text"), "")

    def test_the_growing_last_step_of_a_recording_is_not_marked(self):
        tree = self.app.step_tree
        self.app.refresh_steps(steps=[Step(40, ("A",)), Step(5, ("B",))], follow=True)
        self.assertEqual(tree.item("1", "tags"), "")
        self.assertEqual(self.app.short_label.cget("text"), "")
        # The recording ends with that step still short: now it is marked.
        self.app.refresh_steps(steps=[Step(40, ("A",)), Step(5, ("B",))])
        self.assertEqual(tree.item("1", "tags"), ("short",))
        self.assertIn("1 in orange", self.app.short_label.cget("text"))

    def test_game_input_rate_sets_the_short_step_limit(self):
        tree = self.app.step_tree
        self.select("Buttons")  # two 30 ms steps
        self.assertEqual(self.app.game_input_var.get(), "60 Hz")
        self.assertEqual(tree.item("0", "tags"), ("short",))
        self.app.set_game_input_rate(144)
        self.assertEqual(self.app.game_input_var.get(), "144 Hz or more")
        self.assertEqual(tree.item("0", "tags"), "")
        self.assertEqual(self.app.short_label.cget("text"), "")
        self.app.game_input_var.set("30 Hz")  # as picked in the list
        self.app.set_game_input_rate()
        self.assertEqual(self.app.short_label.cget("text"), "2 in orange: under 66 ms as played")
        self.assertEqual(AppSettings.load(self.data / "settings.json").game_input_hz, 30)
        self.app.toggle_language()
        self.assertEqual(self.app.game_input_var.get(), "30 Hz")
        self.app.set_game_input_rate(144)
        self.assertEqual(self.app.game_input_var.get(), "144 Hz 以上")
        # A value from a hand-edited settings file that is not offered falls back to 60.
        (self.data / "odd.json").write_text('{"game_input_hz": 75}', encoding="utf-8")
        self.assertEqual(AppSettings.load(self.data / "odd.json").game_input_hz, 60)

    def test_game_input_rate_help_opens_on_hover(self):
        help_tip = self.app.rate_help
        self.assertIn("16 ms at 144 Hz", help_tip.text)
        help_tip.show()
        self.assertTrue(help_tip.shown)
        help_tip.hide()
        self.assertFalse(help_tip.shown)
        # The limits in the help come from GAME_INPUT_RATES.
        for hz, ms in app_module.GAME_INPUT_RATES.items():
            self.assertIn(f"{ms} ms at {hz} Hz", help_tip.text)

    def test_short_marks_follow_the_playback_speed(self):
        tree = self.app.step_tree
        self.select("Buttons")  # two 30 ms steps, 60 Hz: short at 1x
        self.assertEqual(tree.item("0", "tags"), ("short",))
        self.app.speed_var.set("0.5x")  # plays 60 ms
        self.app._speed_changed()
        self.assertEqual(tree.item("0", "tags"), "")
        self.assertEqual(self.app.short_label.cget("text"), "")
        self.app.speed_var.set("2x")
        self.app._speed_changed()
        self.app.refresh_steps(steps=[Step(50, ("A",))])  # plays 25 ms
        self.assertEqual(tree.item("0", "tags"), ("short",))

    def test_a_short_loop_gap_is_flagged_when_repeating(self):
        self.app.refresh_steps(steps=[Step(100, ("A",))])
        self.app.loops_var.set("1")
        self.app.gap_var.set("20")
        self.assertEqual(self.app.short_label.cget("text"), "")  # played once: no gap
        self.app.loops_var.set("5")
        self.assertEqual(self.app.short_label.cget("text"), "Loop gap: under 33 ms as played")
        self.assertEqual(str(self.app.gap_label.cget("foreground")), app_module.SHORT_STEP_COLOR)
        self.app.gap_var.set("50")
        self.assertEqual(self.app.short_label.cget("text"), "")
        self.app.gap_var.set("0")  # no gap at all is the user's choice
        self.assertEqual(self.app.short_label.cget("text"), "")

    def test_buttons_only_macro_plays_without_claiming_sticks(self):
        self.select("Buttons")
        self.app.start_playback()
        self.pump(0.3)
        connection = self.app.connection
        self.assertEqual(connection.claims, [])
        self.assertEqual([state for state, _left in connection.client.states[:2]], [("A",), ("B",)])
        self.assertEqual(connection.client.released, 1)
        self.assertIn("Playback finished", self.app.status_label.cget("text"))

    def test_finished_recording_reports_missed_frames(self):
        class Recorded:
            error = None
            frames_missed = 3
            frames_total = 120

            def stop(self):
                return [Step(30, ("A",))]

        self.app.recorder = Recorded()
        self.app._finish_recording()
        self.assertIn("3/120 frames were missed", self.app.status_text)
        Recorded.frames_missed = 0
        self.app.recorder = Recorded()
        self.app._finish_recording()
        self.assertNotIn("missed", self.app.status_text)

    def test_status_line_follows_a_language_switch(self):
        self.app.toggle_language()  # zh: record finds nothing
        self.app._set_status("沒有錄到任何輸入。")
        self.pump(0.1)
        self.assertIn("沒有錄到任何輸入。", self.app.status_label.cget("text"))
        self.app.toggle_language()  # back to English
        self.pump(0.1)
        self.assertIn("No input was recorded.", self.app.status_label.cget("text"))
        self.assertNotIn("沒有", self.app.status_label.cget("text"))

    def test_skipped_stick_warning_is_translated_when_shown(self):
        self.app._status = ((
            "{sticks}正由其他擴充工具控制，播放時會略過搖桿動作。",
            {"sticks": lambda: self.app._stick_names({"left", "right"})},
        ),)
        self.assertIn("controls the Left stick and Right stick", self.app.status_text)
        self.app.toggle_language()
        self.assertTrue(self.app.status_text.startswith("左搖桿、右搖桿正由"), self.app.status_text)

    def test_every_chinese_text_has_an_english_translation(self):
        import ast
        import re

        from s2p_macro.i18n import EN

        cjk = re.compile(r"[㐀-鿿　-〿＀-￯]")
        allowed = {"中", "、"}  # the language button and the Chinese list separator
        package = Path(app_module.__file__).resolve().parent
        missing = []
        for path in sorted(package.glob("*.py")):
            if path.name in ("i18n.py", "tooltip_layout.py"):  # not UI text
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                        and cjk.search(node.value) and node.value not in EN
                        and node.value not in allowed):
                    missing.append(f"{path.name}:{node.lineno}: {node.value}")
        self.assertEqual(missing, [])

    def test_stick_macro_claims_the_stick_then_gives_it_back(self):
        self.select("Stick")
        self.app.start_playback()
        self.assertIn("Taking control", self.app.status_text)
        connection = self.app.connection
        self.assertEqual(connection.claims, [("left",)])
        playing_client = connection.client
        self.pump(0.4)
        self.assertEqual(playing_client.states[1], (("B",), (0, 1000)))
        # After playback the claim is released for other tools.
        self.assertEqual(connection.claims, [("left",), ()])

    def test_recording_shows_steps_live_and_lists_the_new_macro(self):
        client = self.app.connection.client
        client.frames = [
            {"frame": 1, "buttons": ["A"]}, {"frame": 2, "buttons": ["A"]},
            {"frame": 3, "buttons": ["A", "X"]},
        ]
        self.app.start_recording()
        self.assertEqual(self.app.macro_list.get("end"), "● Recording…")
        self.pump(0.3)
        rows = [self.app.step_tree.set(item, "buttons") for item in self.app.step_tree.get_children()]
        self.assertEqual(rows, ["A", "A + X"])
        self.app.stop_all()
        names = self.app.macro_list.get(0, "end")
        self.assertEqual(len(names), 3)
        self.assertTrue(self.app.macro.name.startswith("Rec "))
        self.assertNotIn("● Recording…", names)

    def test_controller_trigger_plays_and_stops_the_macro(self):
        library = MacroLibrary(self.data / "macros")
        library.save(Macro("Long", [Step(3000, ("X",))], trigger=("BACK", "Y")))
        self.app.refresh_macro_list("Buttons")
        self.assertEqual(self.app._triggers, {"Long": ("Y", "BACK")})
        self.pump(0.2)
        self.assertIsNotNone(self.app._trigger_monitor)  # read is granted
        self.app._trigger_events.put("Long")  # what the monitor reports
        self.pump(0.2)
        self.assertEqual(self.app.macro.name, "Long")
        self.assertTrue(self.app.player.running)
        self.assertEqual(self.app.trigger_label.cget("text"), "Y + BACK")
        self.app._trigger_events.put("Long")  # same combination again: stop
        self.pump(0.2)
        self.assertFalse(self.app.player.running)
        self.assertEqual(self.app.connection.client.released, 1)

    def test_trigger_monitor_needs_read_permission(self):
        MacroLibrary(self.data / "macros").save(Macro("T", [Step(30)], trigger=("A", "B")))
        self.app.connection.client.granted = {"input"}
        self.app.refresh_macro_list()
        self.pump(0.2)
        self.assertIsNone(self.app._trigger_monitor)
        self.assertIn("Allow reading controller state", self.app.status_label.cget("text"))

    def test_close_button_hides_to_tray_and_stays_connected(self):
        with patch.object(app_module.messagebox, "showinfo") as hint:
            self.app.hide_to_tray()
            self.app.hide_to_tray()
        hint.assert_called_once()  # the tray hint is shown only the first time
        self.assertTrue(self.app.tray.visible)
        self.assertEqual(self.root.state(), "withdrawn")
        self.assertIsNotNone(self.app.client)  # still connected to S2P
        self.app.tray.actions.append("show")
        self.pump(0.2)
        self.assertFalse(self.app.tray.visible)
        self.assertNotEqual(self.root.state(), "withdrawn")

    def test_started_by_s2p_goes_straight_to_the_tray(self):
        root = tk.Tk()
        app = app_module.MacroApp(
            root, data_dir=self.data, connection_factory=FakeConnection,
            tray_factory=FakeTray, start_hidden=True,
        )
        self.addCleanup(lambda: root.winfo_exists() and app.close())
        self.assertEqual(root.state(), "withdrawn")
        self.assertTrue(app.tray.visible)
        app.connection.start()
        self.assertIsNotNone(app.client)  # connects without a window

    def test_background_start_still_shows_the_notice_the_first_time(self):
        data = self.data / "fresh"
        AppSettings(notice_accepted=False).save(data / "settings.json")
        root = tk.Tk()
        with patch.object(app_module.MacroApp, "show_notice", return_value=True) as notice:
            app = app_module.MacroApp(
                root, data_dir=data, connection_factory=FakeConnection,
                tray_factory=FakeTray, start_hidden=True,
            )
        self.addCleanup(lambda: root.winfo_exists() and app.close())
        notice.assert_called_once()
        self.assertNotEqual(root.state(), "withdrawn")

    def test_background_flag_comes_from_s2p(self):
        with patch.dict(app_module.os.environ, {"S2P_EXTENSION_BACKGROUND": "1"}):
            self.assertTrue(app_module.started_in_background())
        with patch.dict(app_module.os.environ, {}, clear=True), \
                patch.object(app_module.sys, "argv", ["S2P-Joystick-Macro.exe"]):
            self.assertFalse(app_module.started_in_background())

    def test_second_launch_shows_the_hidden_window(self):
        with patch.object(app_module.messagebox, "showinfo"):
            self.app.hide_to_tray()
        self.app._show_requests.put("show")  # what SingleInstance reports
        self.pump(0.2)
        self.assertNotEqual(self.root.state(), "withdrawn")

    def test_open_restores_a_minimized_window_and_brings_it_to_front(self):
        self.root.deiconify()
        self.root.iconify()
        self.pump(0.1)
        self.assertEqual(self.root.state(), "iconic")
        with patch.object(app_module, "bring_to_front") as front:
            self.app._show_requests.put("show")  # S2P's Open on a running copy
            self.pump(0.2)
        self.assertEqual(self.root.state(), "normal")
        front.assert_called_once_with(self.root)

    def test_closing_s2p_closes_the_tool(self):
        self.select("Buttons")
        self.app.start_playback()
        client = self.app.connection.client
        tray = self.app.tray
        self.app.connection.on_host_exit()  # what the host watcher reports
        self.pump(0.2)
        self.assertTrue(tray.stopped)
        self.assertGreaterEqual(client.released, 1)  # playback released its input
        with self.assertRaises(tk.TclError):
            self.root.winfo_exists() and self.root.state()

    def test_tray_exit_really_quits(self):
        tray = self.app.tray
        tray.actions.append("exit")
        self.pump(0.2)
        self.assertTrue(tray.stopped)
        with self.assertRaises(tk.TclError):
            self.root.winfo_exists() and self.root.state()

    def test_record_requires_read_permission(self):
        self.app.connection.client.granted = {"input"}
        with patch.object(app_module.messagebox, "showwarning") as warning:
            self.app.start_recording()
        warning.assert_called_once()
        self.assertIsNone(self.app.recorder)


if __name__ == "__main__":
    unittest.main()
