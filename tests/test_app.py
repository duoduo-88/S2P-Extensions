"""Smoke test of the Tk window with a fake S2P connection."""

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

    def test_buttons_only_macro_plays_without_claiming_sticks(self):
        self.select("Buttons")
        self.app.start_playback()
        self.pump(0.3)
        connection = self.app.connection
        self.assertEqual(connection.claims, [])
        self.assertEqual([state for state, _left in connection.client.states[:2]], [("A",), ("B",)])
        self.assertEqual(connection.client.released, 1)
        self.assertIn("Playback finished", self.app.status_label.cget("text"))

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
