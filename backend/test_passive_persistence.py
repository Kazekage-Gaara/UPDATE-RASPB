"""Regression tests without importing Celery or contacting gateways."""
import ast
from pathlib import Path
import re
import unittest
from unittest.mock import Mock


class PassivePersistenceTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path(__file__).with_name("tasks.py").read_text())
        names = {"run_passive_persistence_probe", "read_passive_persistence_probe"}
        module = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
        self.ns = {"re": re, "PASSIVE_PERSISTENCE_PROBE_PATH": "/test/probe"}
        exec(compile(module, "tasks.py", "exec"), self.ns)
        self.read = self.ns["read_passive_persistence_probe"]
        self.ns.update(
            get_passive_persistence_state=Mock(return_value={"token": "saved", "boot_id": "old"}),
            read_passive_persistence_probe=Mock(),
            write_passive_persistence_probe=Mock(return_value="new"),
            save_diagnostic_event=Mock(),
        )

    def test_missing_after_reboot_is_not_confirmed_frozen(self):
        self.ns["read_passive_persistence_probe"].return_value = {"boot_id": "new", "marker": "MISSING"}
        result = self.ns["run_passive_persistence_probe"]("test")
        self.assertFalse(result.get("frozen"))
        self.assertEqual(self.ns["save_diagnostic_event"].call_args.args[1], "PERSISTENCE_UNVERIFIED")

    def test_marker_survives_multiple_reboots(self):
        for boot in ("new", "another"):
            self.ns["read_passive_persistence_probe"].return_value = {"boot_id": boot, "marker": "saved"}
            result = self.ns["run_passive_persistence_probe"]("test")
            self.assertTrue(result["verified"])
            self.assertEqual(result["token"], "saved")
        self.ns["write_passive_persistence_probe"].assert_not_called()

    def test_other_token_does_not_prove_frozen(self):
        self.ns["read_passive_persistence_probe"].return_value = {"boot_id": "new", "marker": "other"}
        self.assertFalse(self.ns["run_passive_persistence_probe"]("test").get("frozen"))
        self.ns["save_diagnostic_event"].assert_not_called()

    def test_incomplete_ssh_output_is_inconclusive(self):
        self.ns["run_ssh_command"] = Mock(return_value={"success": True, "output": "PASSIVE_BOOT_ID:abcd"})
        self.assertEqual(self.read("test"), {})


if __name__ == "__main__":
    unittest.main()
