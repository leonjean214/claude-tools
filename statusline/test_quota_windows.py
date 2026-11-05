#!/usr/bin/env python3
"""额度窗口显示适配测试：Claude Ultra (five_hour=null) / ChatGPT Pro (primary=7d, secondary=null) + 旧格式。

运行: python3 -m unittest statusline/test_quota_windows.py -v
     或 cd statusline && python3 -m unittest test_quota_windows -v
"""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

STATUSLINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(STATUSLINE_DIR))  # usage 依赖同目录的 ai_models


def load_module(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, str(STATUSLINE_DIR / filename))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclass 处理要在 sys.modules 里找到本模块
    spec.loader.exec_module(mod)
    return mod


usage = load_module("usage_script", "usage")
cqw = load_module("codex_quota_watch", "codex-quota-watch")
tt = load_module("tt_statusline", "tt-statusline.py")

RESET_TS = int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp())
RESET_ISO = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj))


class ClaudeStatusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.status_file = Path(self.tmp.name) / "tt-status.json"
        self.patcher = mock.patch.object(usage, "CLAUDE_STATUS", self.status_file)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_old_format_both_windows(self):
        write_json(self.status_file, {"rate_limits": {
            "five_hour": {"used_percentage": 42, "resets_at": RESET_TS},
            "seven_day": {"used_percentage": 12, "resets_at": RESET_TS},
        }})
        status = usage.claude_status()
        self.assertEqual(status["5h"].used_pct, 42)
        self.assertFalse(status["5h"].missing)
        self.assertEqual(status["7d"].used_pct, 12)
        self.assertFalse(status["7d"].missing)

    def test_ultra_five_hour_null(self):
        write_json(self.status_file, {"rate_limits": {
            "five_hour": None,
            "seven_day": {"used_percentage": 33, "resets_at": RESET_TS},
        }})
        status = usage.claude_status()
        self.assertTrue(status["5h"].missing)
        self.assertIsNone(status["5h"].used_pct)
        self.assertEqual(status["7d"].used_pct, 33)
        self.assertFalse(status["7d"].missing)


class CodexStatusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.status_file = Path(self.tmp.name) / "quota-status.json"
        self.patcher = mock.patch.object(usage, "CODEX_STATUS", self.status_file)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_old_format_both_windows(self):
        write_json(self.status_file, {
            "primary": {"usedPercent": 60, "windowDurationMins": 300, "resetsAt": RESET_TS},
            "weekly": {"usedPercent": 20, "windowDurationMins": 10080, "resetsAt": RESET_TS},
        })
        status = usage.codex_status()
        self.assertEqual(status["5h"].used_pct, 60)
        self.assertFalse(status["5h"].missing)
        self.assertEqual(status["7d"].used_pct, 20)
        self.assertFalse(status["7d"].missing)

    def test_legacy_format_no_duration(self):
        write_json(self.status_file, {
            "primary": {"usedPercent": 55, "resetsAt": RESET_TS},
            "weekly": {"usedPercent": 15, "resetsAt": RESET_TS},
        })
        status = usage.codex_status()
        self.assertEqual(status["5h"].used_pct, 55)
        self.assertEqual(status["7d"].used_pct, 15)

    def test_pro_primary_is_seven_day(self):
        write_json(self.status_file, {
            "primary": {"usedPercent": 40, "windowDurationMins": 10080, "resetsAt": RESET_TS},
            "weekly": None,
        })
        status = usage.codex_status()
        self.assertTrue(status["5h"].missing)
        self.assertEqual(status["7d"].used_pct, 40)
        self.assertFalse(status["7d"].missing)


class FallbackStatusTest(unittest.TestCase):
    def test_missing_window_marked(self):
        out = usage.fallback_status(
            [sys.executable, "-c", "print('7d  [##########----------] 50%')"], "claude")
        self.assertEqual(out["7d"].used_pct, 50)
        self.assertTrue(out["5h"].missing)

    def test_no_output_stays_unknown(self):
        out = usage.fallback_status([sys.executable, "-c", "pass"], "claude")
        self.assertIsNone(out["5h"].used_pct)
        self.assertFalse(out["5h"].missing)
        self.assertFalse(out["7d"].missing)


class PrintServiceTest(unittest.TestCase):
    def render(self, status):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            usage.print_service(
                "Claude", status, usage.UsageCost(1.0, 2.0, month=3.0),
                (datetime.now().astimezone(), datetime.now().astimezone()))
        return buf.getvalue()

    def test_missing_5h_shows_no_limit(self):
        out = self.render({
            "5h": usage.WindowStatus(missing=True),
            "7d": usage.WindowStatus(30, datetime.now().astimezone() + timedelta(days=2)),
        })
        self.assertIn("无 5h 限制", out)
        self.assertIn("7d", out)
        self.assertIn("30%", out)

    def test_old_format_unchanged(self):
        out = self.render({
            "5h": usage.WindowStatus(42, datetime.now().astimezone() + timedelta(hours=2)),
            "7d": usage.WindowStatus(30, datetime.now().astimezone() + timedelta(days=2)),
        })
        self.assertIn("5h", out)
        self.assertIn("42%", out)
        self.assertNotIn("无", out)


class CodexQuotaWatchTest(unittest.TestCase):
    PRO_STATUS = {
        "updatedAt": "2026-11-04T12:00:00+08:00",
        "planType": "pro",
        "primary": {"usedPercent": 40, "windowDurationMins": 10080, "resetsAt": RESET_TS},
        "weekly": None,
    }
    OLD_STATUS = {
        "updatedAt": "2026-11-04T12:00:00+08:00",
        "planType": "plus",
        "primary": {"usedPercent": 60, "windowDurationMins": 300, "resetsAt": RESET_TS},
        "weekly": {"usedPercent": 20, "windowDurationMins": 10080, "resetsAt": RESET_TS},
    }

    def capture(self, status):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cqw.print_status(status)
        return buf.getvalue()

    def test_print_status_old_format(self):
        out = self.capture(self.OLD_STATUS)
        self.assertIn("5h:", out)
        self.assertIn("7d:", out)

    def test_print_status_pro_only_weekly(self):
        out = self.capture(self.PRO_STATUS)
        self.assertNotIn("5h", out)
        self.assertIn("7d:", out)
        self.assertIn("40%", out)

    def test_labels(self):
        self.assertEqual(cqw.window_label("primary", {"windowDurationMins": 10080}), "7d")
        self.assertEqual(cqw.window_label("primary", {"windowDurationMins": 300}), "5h")
        self.assertEqual(cqw.window_label("primary", {}), "5h")
        self.assertEqual(cqw.window_label("weekly", {}), "7d")
        self.assertEqual(cqw.notify_label("primary", {"windowDurationMins": 10080}), "7 天额度")
        self.assertEqual(cqw.notify_label("primary", {"windowDurationMins": 300}), "5 小时额度")

    def test_notify_crossings_skips_absent_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(cqw, "STATE_FILE", Path(tmp) / "state.json"), \
                 mock.patch.object(cqw, "notify") as notify:
                status = dict(self.PRO_STATUS)
                status["primary"] = dict(status["primary"], usedPercent=90)
                cqw.notify_crossings(status)
        self.assertTrue(notify.called)
        for call in notify.call_args_list:
            self.assertIn("7 天额度", call.args[0])  # 90% 跨过 75/90 两个阈值
            self.assertNotIn("小时", call.args[0])


class TtStatuslineRenderTest(unittest.TestCase):
    def render(self, data, codex=None):
        now = datetime.now(timezone.utc)
        buf = io.StringIO()
        with mock.patch.object(tt, "get_width", return_value=116), \
             mock.patch.object(tt, "load_codex_status", return_value=(codex, 30 if codex else None)), \
             mock.patch.object(tt, "load_usage_costs", return_value=({}, 0)):
            with contextlib.redirect_stdout(buf):
                tt.render(data, now)
        return tt.ANSI_RE.sub("", buf.getvalue())

    def test_ultra_hides_5h_keeps_7d(self):
        out = self.render({"rate_limits": {
            "five_hour": None,
            "seven_day": {"used_percentage": 30, "resets_at": RESET_TS},
        }})
        self.assertNotIn("5h", out)
        self.assertIn("7d", out)
        self.assertIn("30%", out)

    def test_old_format_shows_both(self):
        out = self.render({"rate_limits": {
            "five_hour": {"used_percentage": 42, "resets_at": RESET_TS},
            "seven_day": {"used_percentage": 30, "resets_at": RESET_TS},
        }})
        self.assertIn("5h", out)
        self.assertIn("7d", out)

    def test_codex_pro_labels_primary_as_7d(self):
        out = self.render({"rate_limits": {}}, codex={
            "primary": {"usedPercent": 40, "windowDurationMins": 10080, "resetsAt": RESET_TS},
            "weekly": None,
        })
        self.assertIn("Codex", out)
        self.assertNotIn("5h", out)
        self.assertIn("7d", out)
        self.assertIn("40%", out)

    def test_codex_old_format_shows_both(self):
        out = self.render({"rate_limits": {}}, codex={
            "primary": {"usedPercent": 60, "windowDurationMins": 300, "resetsAt": RESET_TS},
            "weekly": {"usedPercent": 20, "windowDurationMins": 10080, "resetsAt": RESET_TS},
        })
        self.assertIn("5h", out)
        self.assertIn("7d", out)


if __name__ == "__main__":
    unittest.main()
