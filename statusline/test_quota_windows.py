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

    def assert_both_unknown(self, status):
        for key in ("5h", "7d"):
            self.assertFalse(status[key].missing, key)
            self.assertIsNone(status[key].used_pct, key)

    def test_rate_limits_null_is_unknown(self):
        write_json(self.status_file, {"rate_limits": None})
        self.assert_both_unknown(usage.claude_status())

    def test_rate_limits_absent_is_unknown(self):
        write_json(self.status_file, {"model": {"id": "claude-opus"}})
        self.assert_both_unknown(usage.claude_status())

    def test_rate_limits_empty_is_unknown(self):
        write_json(self.status_file, {"rate_limits": {}})
        self.assert_both_unknown(usage.claude_status())

    def test_non_object_cache_is_unknown(self):
        for value in ([1], "invalid", 12, True):
            with self.subTest(value=value):
                write_json(self.status_file, value)
                self.assert_both_unknown(usage.claude_status())

    def test_both_windows_null(self):
        write_json(self.status_file, {"rate_limits": {"five_hour": None, "seven_day": None}})
        status = usage.claude_status()
        self.assertTrue(status["5h"].missing)
        self.assertTrue(status["7d"].missing)

    def test_print_service_null_rate_limits_not_no_limit(self):
        write_json(self.status_file, {"rate_limits": None})
        now = usage.now_local()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            usage.print_service("Claude", usage.claude_status(), usage.UsageCost(), (now, now))
        out = buf.getvalue()
        self.assertIn("??%", out)
        self.assertNotIn("无 5h 限制", out)
        self.assertNotIn("无 7d 限制", out)

    def test_print_service_both_null_shows_no_limit(self):
        write_json(self.status_file, {"rate_limits": {"five_hour": None, "seven_day": None}})
        now = usage.now_local()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            usage.print_service("Claude", usage.claude_status(), usage.UsageCost(), (now, now))
        out = buf.getvalue()
        self.assertIn("无 5h 限制", out)
        self.assertIn("无 7d 限制", out)


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

    def test_absent_fields_stay_unknown(self):
        write_json(self.status_file, {"updatedAt": "test"})
        status = usage.codex_status()
        for slot in ("5h", "7d"):
            self.assertIsNone(status[slot].used_pct)
            self.assertFalse(status[slot].missing)

    def test_missing_or_invalid_window_stays_unknown(self):
        for name, slot, other, other_slot in (
            ("primary", "5h", "weekly", "7d"),
            ("weekly", "7d", "primary", "5h"),
        ):
            for value in ("absent", "invalid", 12, [], {}):
                with self.subTest(name=name, value=value):
                    data = {other: {"usedPercent": 25, "resetsAt": RESET_TS}}
                    if value != "absent":
                        data[name] = value
                    write_json(self.status_file, data)
                    status = usage.codex_status()
                    self.assertIsNone(status[slot].used_pct)
                    self.assertFalse(status[slot].missing)
                    self.assertEqual(status[other_slot].used_pct, 25)
                    self.assertFalse(status[other_slot].missing)

    def test_invalid_percentage_is_unknown_not_missing(self):
        for value in ({}, {"usedPercent": "?"}):
            with self.subTest(value=value):
                write_json(self.status_file, {"primary": value, "weekly": value})
                for window in usage.codex_status().values():
                    self.assertIsNone(window.used_pct)
                    self.assertFalse(window.missing)

    def test_explicit_null_windows(self):
        for data, missing, known in (
            ({"primary": None, "weekly": {"usedPercent": 25}}, "5h", "7d"),
            ({"primary": {"usedPercent": 25}, "weekly": None}, "7d", "5h"),
        ):
            with self.subTest(missing=missing):
                write_json(self.status_file, data)
                status = usage.codex_status()
                self.assertTrue(status[missing].missing)
                self.assertIsNone(status[missing].used_pct)
                self.assertEqual(status[known].used_pct, 25)
                self.assertFalse(status[known].missing)
        write_json(self.status_file, {"primary": None, "weekly": None})
        self.assertTrue(all(window.missing for window in usage.codex_status().values()))

    def test_pro_missing_or_invalid_secondary_is_unknown(self):
        for value in ("absent", "invalid", 12, [], {}):
            with self.subTest(value=value):
                data = {"primary": {
                    "usedPercent": 40, "windowDurationMins": 10080, "resetsAt": RESET_TS,
                }}
                if value != "absent":
                    data["weekly"] = value
                write_json(self.status_file, data)
                status = usage.codex_status()
                self.assertIsNone(status["5h"].used_pct)
                self.assertFalse(status["5h"].missing)
                self.assertEqual(status["7d"].used_pct, 40)
                self.assertFalse(status["7d"].missing)

    def test_non_object_cache_is_unknown(self):
        for value in ([1], "invalid", 12, True):
            with self.subTest(value=value):
                write_json(self.status_file, value)
                for window in usage.codex_status().values():
                    self.assertIsNone(window.used_pct)
                    self.assertFalse(window.missing)

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
    def parse(self, stdout, parser):
        result = mock.Mock(stdout=stdout, returncode=0)
        with mock.patch.object(usage.subprocess, "run", return_value=result):
            return usage.fallback_status(["mock-quota", "--status"], parser)

    def line(self, parser, slot, percent):
        if parser == "claude":
            return f"{slot}  [##########----------] {percent}%"
        return f"{slot}: 已使用 {percent}% | 重置 未知时间"

    def test_omitted_window_stays_unknown(self):
        for parser in ("claude", "codex"):
            for known, unknown in (("7d", "5h"), ("5h", "7d")):
                with self.subTest(parser=parser, known=known):
                    out = self.parse(self.line(parser, known, 50), parser)
                    self.assertEqual(out[known].used_pct, 50)
                    self.assertFalse(out[known].missing)
                    self.assertIsNone(out[unknown].used_pct)
                    self.assertFalse(out[unknown].missing)

    def test_unparseable_window_stays_unknown(self):
        for parser in ("claude", "codex"):
            for bad in (self.line(parser, "5h", "?"), "5h: unavailable"):
                with self.subTest(parser=parser, bad=bad):
                    out = self.parse(bad + "\n" + self.line(parser, "7d", 50), parser)
                    self.assertEqual(out["7d"].used_pct, 50)
                    self.assertIsNone(out["5h"].used_pct)
                    self.assertFalse(out["5h"].missing)

    def test_no_output_stays_unknown(self):
        for parser in ("claude", "codex"):
            with self.subTest(parser=parser):
                out = self.parse("", parser)
                for window in out.values():
                    self.assertIsNone(window.used_pct)
                    self.assertFalse(window.missing)

    def test_command_failure_stays_unknown(self):
        for parser in ("claude", "codex"):
            with self.subTest(parser=parser), \
                 mock.patch.object(usage.subprocess, "run", side_effect=OSError("unavailable")):
                out = usage.fallback_status(["mock-quota", "--status"], parser)
                for window in out.values():
                    self.assertIsNone(window.used_pct)
                    self.assertFalse(window.missing)


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

    def test_codex_unknown_cache_render(self):
        for unknown, known, data in (
            ("5h", "7d", {"weekly": {"usedPercent": 25}}),
            ("7d", "5h", {"primary": {"usedPercent": 25}}),
            ("5h", "7d", {
                "primary": {"usedPercent": 25, "windowDurationMins": 10080},
                "weekly": "invalid",
            }),
        ):
            with self.subTest(unknown=unknown, data=data), \
                 mock.patch.object(usage, "load_json", return_value=data):
                status = usage.codex_status()
                out = self.render(status)
                self.assertIn("??%", out)
                self.assertNotIn(f"无 {unknown} 限制", out)
                self.assertNotIn(f"无 {known} 限制", out)
                self.assertIn("25%", out)

    def test_codex_explicit_null_cache_render(self):
        for data, missing in (
            ({"primary": None, "weekly": {"usedPercent": 25}}, "5h"),
            ({"primary": {"usedPercent": 25}, "weekly": None}, "7d"),
            ({"primary": {"usedPercent": 25, "windowDurationMins": 10080},
              "weekly": None}, "5h"),
        ):
            with self.subTest(missing=missing, data=data), \
                 mock.patch.object(usage, "load_json", return_value=data):
                out = self.render(usage.codex_status())
                self.assertIn(f"无 {missing} 限制", out)
                self.assertIn("25%", out)
                self.assertNotIn("??%", out)
        with mock.patch.object(usage, "load_json", return_value={"primary": None, "weekly": None}):
            out = self.render(usage.codex_status())
        self.assertIn("无 5h 限制", out)
        self.assertIn("无 7d 限制", out)

    def test_fallback_unknown_render(self):
        for parser in ("claude", "codex"):
            stdout = ("5h [----] ?%\n7d [####] 25%" if parser == "claude"
                      else "5h: 已使用 ?%\n7d: 已使用 25%")
            with self.subTest(parser=parser), \
                 mock.patch.object(usage.subprocess, "run", return_value=mock.Mock(stdout=stdout)):
                out = self.render(usage.fallback_status(["mock-quota"], parser))
            self.assertIn("??%", out)
            self.assertIn("25%", out)
            self.assertNotIn("无 5h 限制", out)
            self.assertNotIn("无 7d 限制", out)

    def test_quota_wait_missing_reset_render(self):
        quota_wait = load_module("quota_wait_script", "../mac/quota-wait")
        buf = io.StringIO()
        windows = quota_wait.parse_windows({
            "five_hour": {"utilization": 15},
            "seven_day": {"utilization": 25, "resets_at": RESET_ISO},
        })
        quota_wait.print_status(windows, file=buf)
        self.assertNotIn("5h", buf.getvalue())
        self.assertIn("7d", buf.getvalue())
        with mock.patch.object(usage.subprocess, "run", return_value=mock.Mock(stdout=buf.getvalue())):
            status = usage.fallback_status(["mock-quota-wait", "--status"], "claude")
        self.assertFalse(status["5h"].missing)
        self.assertIsNone(status["5h"].used_pct)
        out = self.render(status)
        self.assertIn("??%", out)
        self.assertIn("25%", out)
        self.assertNotIn("无 5h 限制", out)

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
