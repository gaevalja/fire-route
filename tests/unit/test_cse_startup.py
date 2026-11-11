"""Regression for the observed banner-only upstream config-path rejection.

These are startup adapter tests, not claims that an actual CSE has started.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("fireroute_cse_entrypoint", ROOT / "infra/cse/entrypoint.py")
entrypoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrypoint)


class CSEStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.ini"
        self.source.write_text("[basic.config]\ncseType=IN\n")
        self.runtime = self.root / "data"

    def test_config_is_staged_and_cli_gets_only_basename(self):
        target = entrypoint.stage_config(self.source, self.runtime)
        command = entrypoint.command_for(target, self.runtime)
        filename = command[command.index("--config") + 1]
        self.assertEqual(filename, target.name)
        self.assertNotIn("/", filename)
        self.assertFalse(Path(filename).is_absolute())
        self.assertEqual(command[command.index("-dir") + 1], str(self.runtime))
        self.assertEqual(target.read_bytes(), self.source.read_bytes())

    def test_user_acme_ini_preserved(self):
        self.runtime.mkdir()
        user_config = self.runtime / "acme.ini"
        user_config.write_text("user-owned configuration")
        target = entrypoint.stage_config(self.source, self.runtime)
        self.assertNotEqual(target, user_config)
        self.assertEqual(user_config.read_text(), "user-owned configuration")

    def test_same_source_reuses_identical_file(self):
        first = entrypoint.stage_config(self.source, self.runtime)
        self.assertEqual(entrypoint.stage_config(self.source, self.runtime), first)
        self.assertEqual(len(list(self.runtime.glob("*.ini"))), 1)

    def test_changed_source_gets_new_file_and_keeps_old(self):
        first = entrypoint.stage_config(self.source, self.runtime)
        before = first.read_bytes()
        self.source.write_text("[basic.config]\ncseType=MN\n")
        second = entrypoint.stage_config(self.source, self.runtime)
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), before)
        self.assertEqual(second.read_bytes(), self.source.read_bytes())

    def test_modified_managed_file_not_overwritten(self):
        target = entrypoint.stage_config(self.source, self.runtime)
        target.write_text("manually changed")
        with self.assertRaises(RuntimeError):
            entrypoint.stage_config(self.source, self.runtime)
        self.assertEqual(target.read_text(), "manually changed")

    def test_external_config_path_rejected_by_launcher(self):
        with self.assertRaises(ValueError):
            entrypoint.command_for(self.source, self.runtime)

    def test_headless_set_in_config_instead_of_suppressing_startup_errors(self):
        import configparser
        config = configparser.ConfigParser(interpolation=None)
        config.read(ROOT / "infra/cse/acme.ini")
        self.assertTrue(config.getboolean("console", "headless"))
        target = entrypoint.stage_config(self.source, self.runtime)
        self.assertNotIn("--headless", entrypoint.command_for(target, self.runtime))
