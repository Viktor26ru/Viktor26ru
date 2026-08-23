import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "ops_control"
sys.path.insert(0, str(ROOT))

from bots import start_code  # noqa: E402
from commands import CommandRouter, _resolve_project, _unit_alias  # noqa: E402
from inventory import PROJECTS, all_hosts, project_by_id  # noqa: E402
from recovery import restart_hint  # noqa: E402
from store import Store  # noqa: E402


class InventoryTests(unittest.TestCase):
    def test_three_projects(self):
        self.assertEqual([p["id"] for p in PROJECTS], ["x5", "chizhik", "pm"])

    def test_hosts(self):
        ids = [h["id"] for h in all_hosts()]
        self.assertEqual(ids, ["cursordev", "x5", "chizhik", "pm"])

    def test_x5_heal_allowlist(self):
        x5 = project_by_id("x5")
        self.assertIn("max-chat-collector.service", x5["heal_units"])
        self.assertTrue(x5["http"])

    def test_restart_hint(self):
        self.assertEqual(restart_hint("x5", "max-chat-collector.service"), "/restart x5 collector")
        self.assertEqual(restart_hint("chizhik", "ie-bot-parallel-collector.service"), "/restart chizhik collector")


class StoreTests(unittest.TestCase):
    def test_uptime_and_admin(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = Store(Path(tmp) / "t.sqlite")
            st.put_snapshot("x5", {"ok": True})
            st.put_snapshot("x5", {"ok": True})
            st.put_snapshot("x5", {"ok": False})
            ratio = st.uptime_ratio("x5", 24)
            self.assertAlmostEqual(ratio, 2 / 3)
            st.add_admin(1, "viktor")
            self.assertTrue(st.is_admin(1))
            st.open_incident("x5", "disk:/", "warning", "hot")
            self.assertEqual(len(st.open_incidents()), 1)
            st.resolve_by_target("x5", "disk:/", "ok")
            self.assertEqual(len(st.open_incidents()), 0)
            st.close()


class CommandTests(unittest.TestCase):
    def test_start_code(self):
        self.assertEqual(start_code("/start 13e06b01"), "13e06b01")
        self.assertEqual(start_code("/start@Crazynewaibot 13e06b01"), "13e06b01")
        self.assertEqual(start_code("/start"), "")

    def test_aliases(self):
        self.assertEqual(_resolve_project("статус пятёрочки"), "x5")
        self.assertEqual(_resolve_project("рестарт чижик"), "chizhik")
        self.assertEqual(_resolve_project("/pm"), "pm")
        self.assertEqual(_unit_alias("x5", "collector"), "max-chat-collector.service")
        self.assertEqual(_unit_alias("chizhik", "dashboard"), "ie-bot-parallel-chizhik-dashboard.service")

    def test_help_and_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = Store(Path(tmp) / "t.sqlite")
            st.put_snapshot("x5", {"ok": True, "title": "Пятёрочка", "load": [0.1, 0.1, 0.1], "mem": {"pct": 20}, "disks": [{"mount": "/", "pct": 40}], "max": {"ok": True, "name": "Aiktor", "username": "bot"}})
            router = CommandRouter(st)
            help_text = router.handle("test", "u", "/help")
            self.assertIn("/status", help_text)
            status = router.handle("test", "u", "статус")
            self.assertIn("Пятёрочка", status)
            st.close()


if __name__ == "__main__":
    unittest.main()
