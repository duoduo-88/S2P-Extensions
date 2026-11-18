"""The "?" help wraps Chinese text like S2P: units and punctuation stay put."""

import unittest

import _paths  # noqa: F401
from s2p_macro.app import GAME_INPUT_HELP
from s2p_macro.tooltip_layout import wrap_tooltip_text


def measure(text):
    # Roughly Tk's look: full-width characters are twice as wide as ASCII.
    return sum(14 if ord(char) > 0x2E7F else 7 for char in text)


class TooltipLayoutTests(unittest.TestCase):
    def test_help_lines_fit_and_never_start_with_punctuation(self):
        wrapped = wrap_tooltip_text(GAME_INPUT_HELP, 320, measure)
        lines = [line for line in wrapped.split("\n") if line]
        self.assertGreater(len(lines), 4)
        for line in lines:
            self.assertLessEqual(measure(line), 320, line)
            self.assertNotIn(line[0], "，。；：、）")

    def test_numbers_stay_with_their_units(self):
        wrapped = wrap_tooltip_text("短於下列長度的步驟會以橘色標示：60 Hz 為 33 ms，144 Hz 以上為 16 ms。",
                                    120, measure)
        for token in ("60 Hz", "33 ms", "144 Hz", "16 ms"):
            self.assertIn(token, wrapped)

    def test_explicit_paragraphs_are_kept(self):
        self.assertEqual(wrap_tooltip_text("A\n\nB", 320, measure), "A\n\nB")


if __name__ == "__main__":
    unittest.main()
