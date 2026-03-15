import unittest
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "basic_agent_loop.py"
SPEC = importlib.util.spec_from_file_location("basic_agent_loop", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

LabelResolver = MODULE.LabelResolver
AgentConfig = MODULE.AgentConfig
parse_intent = MODULE.parse_intent


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

    def test_parse_move_corner_intent(self):
        intent = parse_intent("move to the top left corner")
        self.assertEqual(intent["action"], "move")
        self.assertEqual(intent["corner"], "top_left")

    def test_parse_pickup_bring_back_intent(self):
        intent = parse_intent("pick up the bottle and bring it back")
        self.assertEqual(intent["action"], "pickup")
        self.assertTrue(intent["bring_back"])


if __name__ == "__main__":
    unittest.main()


