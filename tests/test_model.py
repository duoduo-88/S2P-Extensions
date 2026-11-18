import json
import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401

from s2p_macro.model import (
    Macro,
    MacroFormatError,
    MacroLibrary,
    Step,
    events_to_steps,
    safe_file_stem,
)


class StepTests(unittest.TestCase):
    def test_buttons_are_canonical_and_validated(self):
        self.assertEqual(Step(10, ("y", "A", "lb")).buttons, ("A", "Y", "LB"))
        for bad in (
            dict(duration_ms=0), dict(duration_ms=10, buttons=("TURBO",)),
            dict(duration_ms=10, lt=256), dict(duration_ms=10, left=(40000, 0)),
            dict(duration_ms=True),
        ):
            with self.subTest(bad=bad), self.assertRaises(MacroFormatError):
                Step(**bad)

    def test_neutral_and_stick_use(self):
        self.assertTrue(Step(5).is_neutral)
        step = Step(5, right=(0, 100))
        self.assertFalse(step.is_neutral)
        self.assertTrue(step.uses_stick("right"))
        self.assertFalse(step.uses_stick("left"))


class MacroFileTests(unittest.TestCase):
    def test_round_trip(self):
        macro = Macro("Combo", [Step(50, ("A",)), Step(30, rt=200, left=(1, -2))])
        restored = Macro.from_dict(json.loads(json.dumps(macro.to_dict())))
        self.assertEqual(restored, macro)
        self.assertEqual(restored.total_ms, 80)
        self.assertEqual(restored.sticks_used(), {"left"})

    def test_foreign_or_damaged_files_are_rejected(self):
        for data in (
            {}, {"format": "other"}, {"format": "s2p-macro", "version": 9, "name": "x", "steps": []},
            {"format": "s2p-macro", "version": 1, "name": "", "steps": []},
            {"format": "s2p-macro", "version": 1, "name": "x", "steps": [{"buttons": ["A"]}]},
        ):
            with self.subTest(data=data), self.assertRaises(MacroFormatError):
                Macro.from_dict(data)

    def test_wrongly_typed_step_values_are_format_errors(self):
        # tuple(None) used to raise TypeError, which Import... does not catch.
        for step in (
            {"duration_ms": 10, "left": None}, {"duration_ms": 10, "right": None},
            {"duration_ms": 10, "left": 5}, {"duration_ms": 10, "left": [1]},
            {"duration_ms": 10, "left": [1, 2, 3]}, {"duration_ms": 10, "left": ["a", "b"]},
            {"duration_ms": 10, "lt": None}, {"duration_ms": None},
            {"duration_ms": 10, "buttons": None}, {"duration_ms": 10, "buttons": [None]},
        ):
            data = {"format": "s2p-macro", "version": 1, "name": "x", "steps": [step]}
            with self.subTest(step=step), self.assertRaises(MacroFormatError):
                Macro.from_dict(data)


class RecordingConversionTests(unittest.TestCase):
    def test_changes_become_held_steps_and_trailing_release_is_dropped(self):
        events = [
            (1.000, Step(1, ("A",))),
            (1.120, Step(1, ("A", "B"))),
            (1.200, Step(1)),
            (1.500, Step(1, ("X",))),
            (1.540, Step(1)),
        ]
        steps = events_to_steps(events, end_time=3.0)
        self.assertEqual(
            [(step.duration_ms, step.buttons) for step in steps],
            [(120, ("A",)), (80, ("A", "B")), (300, ()), (40, ("X",))],
        )

    def test_repeated_identical_states_merge(self):
        events = [(0.0, Step(1, ("A",))), (0.01, Step(1, ("A",))), (0.02, Step(1))]
        self.assertEqual(events_to_steps(events, 1.0), [Step(20, ("A",))])

    def test_still_held_at_stop_keeps_its_duration(self):
        self.assertEqual(events_to_steps([(0.0, Step(1, ("B",)))], 0.25), [Step(250, ("B",))])


class LibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.library = MacroLibrary(Path(temporary.name) / "macros")

    def test_save_list_rename_delete(self):
        self.assertEqual(self.library.names(), [])
        self.library.save(Macro("b", [Step(10, ("A",))]))
        self.library.save(Macro("A one", [Step(10)]))
        self.assertEqual(self.library.names(), ["A one", "b"])
        self.library.rename("b", "c")
        self.assertEqual(self.library.names(), ["A one", "c"])
        self.assertEqual(self.library.load("c").steps, [Step(10, ("A",))])
        self.library.delete("A one")
        self.assertEqual(self.library.names(), ["c"])

    def test_damaged_files_are_skipped_in_the_list(self):
        self.library.save(Macro("good", [Step(10)]))
        (self.library.folder / "broken.json").write_text("{", encoding="utf-8")
        self.assertEqual(self.library.names(), ["good"])
        with self.assertRaises(MacroFormatError):
            self.library.load_file(self.library.folder / "broken.json")

    def test_wrongly_typed_files_are_skipped_and_reported(self):
        self.library.save(Macro("good", [Step(10)]))
        bad = self.library.folder / "bad.json"
        bad.write_text(json.dumps({"format": "s2p-macro", "version": 1, "name": "bad",
                                   "steps": [{"duration_ms": 10, "left": None}]}),
                       encoding="utf-8")
        self.assertEqual(self.library.names(), ["good"])  # listing does not crash
        with self.assertRaises(MacroFormatError):
            self.library.load_file(bad)  # Import... shows this as a message

    def test_unsafe_names_stay_inside_the_folder(self):
        self.assertEqual(safe_file_stem('..\\a/b:c*?'), "_a_b_c__")
        macro = Macro("../../escape", [Step(10)])
        self.library.save(macro)
        self.assertEqual(self.library.path_for(macro.name).parent, self.library.folder)
        self.assertEqual(self.library.names(), ["../../escape"])



class TriggerFileTests(unittest.TestCase):
    def test_trigger_round_trip_and_library_map(self):
        macro = Macro("Dash", [Step(10, ("B",))], trigger=("y", "BACK"))
        self.assertEqual(macro.trigger, ("y", "BACK"))
        data = macro.to_dict()
        self.assertEqual(data["trigger"], ["Y", "BACK"])
        self.assertEqual(Macro.from_dict(data).trigger, ("Y", "BACK"))
        self.assertNotIn("trigger", Macro("Plain", [Step(10)]).to_dict())
        with tempfile.TemporaryDirectory() as folder:
            library = MacroLibrary(Path(folder))
            library.save(Macro.from_dict(data))
            library.save(Macro("Plain", [Step(10)]))
            self.assertEqual(library.triggers(), {"Dash": ("Y", "BACK")})

    def test_bad_trigger_is_rejected(self):
        data = Macro("x", [Step(10)]).to_dict()
        for bad in ("A", ["TURBO"]):
            data["trigger"] = bad
            with self.subTest(trigger=bad), self.assertRaises(MacroFormatError):
                Macro.from_dict(data)


if __name__ == "__main__":
    unittest.main()
