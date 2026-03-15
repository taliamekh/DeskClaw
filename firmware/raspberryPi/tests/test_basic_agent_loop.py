import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from basic_agent_loop import LabelResolver, AgentConfig, parse_intent


class BasicAgentLoopTests(unittest.TestCase):
    def setUp(self):
        self.cfg = AgentConfig(
            whisper_url="ws://localhost:8765",
            vision_api_base="http://localhost:8787",
            wake_phrase="hey claw",
        )
        self.resolver = LabelResolver(self.cfg)

    def test_parse_pickup_intent(self):
        intent = parse_intent("please pick up the red noodle package")
        self.assertEqual(intent["action"], "pickup")
        self.assertIn("red noodle package", intent["target_description"])

    def test_parse_find_intent(self):
        intent = parse_intent("hey claw where is the water bottle")
        self.assertEqual(intent["action"], "find")
        self.assertIn("water bottle", intent["target_description"])

    def test_label_fallback_match(self):
        labels = ["bottle", "cup", "book"]
        chosen = self.resolver._fallback_match("can you find my bottle", labels)
        self.assertEqual(chosen, "bottle")


if __name__ == "__main__":
    unittest.main()


