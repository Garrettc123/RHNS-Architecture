import unittest
from metacognition.gate import GenerationBlocked, guarded_generate

class GenerationGateTests(unittest.TestCase):
    def test_commit_invokes_generator_once(self):
        calls = []
        def generate():
            calls.append(True)
            return "generated"
        self.assertEqual(guarded_generate("commit", generate), "generated")
        self.assertEqual(len(calls), 1)

    def test_other_decisions_never_invoke_generator(self):
        for decision in ("continue", "escalate", "abort", "", "unknown", None):
            with self.subTest(decision=decision):
                calls = []
                with self.assertRaises(GenerationBlocked):
                    guarded_generate(decision, lambda: calls.append(True))
                self.assertEqual(calls, [])

    def test_generator_failure_propagates(self):
        def fail():
            raise ValueError("generation failed")
        with self.assertRaises(ValueError):
            guarded_generate("commit", fail)

if __name__ == "__main__":
    unittest.main()
