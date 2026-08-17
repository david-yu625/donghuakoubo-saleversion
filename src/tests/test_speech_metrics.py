from __future__ import annotations

import unittest

from ..core.speech_metrics import (
    count_speech_chars,
    estimate_speech_duration_range,
    estimate_speech_duration_seconds,
)


class SpeechMetricsTest(unittest.TestCase):
    def test_count_ignores_punctuation_and_whitespace(self):
        self.assertEqual(count_speech_chars("标题！\n中文 AI-2，"), 7)

    def test_current_profile_estimate_for_250_chars(self):
        self.assertAlmostEqual(estimate_speech_duration_seconds(250), 250 / 6.0)
        low, high = estimate_speech_duration_range(250)
        self.assertAlmostEqual(low, 37.5)
        self.assertAlmostEqual(high, 250 / 6.0 * 1.1)

if __name__ == "__main__":
    unittest.main()
