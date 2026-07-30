import unittest

from datacloud_platform.contracts import op_result


class ContractsTests(unittest.TestCase):
    def test_op_result_shape(self):
        payload = op_result("x", "done", {"a": 1}, ok=True, warnings=["w"])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "x")
        self.assertEqual(payload["summary"], "done")
        self.assertEqual(payload["details"]["a"], 1)
        self.assertEqual(payload["warnings"], ["w"])


if __name__ == "__main__":
    unittest.main()
