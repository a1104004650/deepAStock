"""技术结构（筹码控盘/交易趋势/支撑压力/指标信号）单元测试 — 纯函数，无网络"""
import unittest
from datetime import date, timedelta

from app.core.market.technical_structure import (
    STAGES, build_technical_structure, chip_analysis, detect_levels,
    detect_signals, trend_stage,
)


def mk_bars(closes, volumes=None, start=date(2026, 1, 1)):
    bars = []
    for i, c in enumerate(closes):
        bars.append({
            "dt": (start + timedelta(days=i)).isoformat(),
            "open": round(c * 0.999, 4), "high": round(c * 1.005, 4),
            "low": round(c * 0.995, 4), "close": round(c, 4),
            "volume": float(volumes[i]) if volumes else 10000.0,
        })
    return bars


class ChipTests(unittest.TestCase):
    def test_flat_price_is_high_concentration(self):
        # 价格长期不变 → 筹码高度集中
        bars = mk_bars([10.0] * 100)
        r = chip_analysis(bars, float_shares=1e8, price=10.0)
        self.assertTrue(r["available"])
        self.assertEqual(r["level"], "高度")
        self.assertLessEqual(r["width90"], 0.18)
        self.assertTrue(0 <= r["winner_rate"] <= 100)
        self.assertTrue(r["peaks"])

    def test_wide_range_is_no_control(self):
        # 价格从50一路走到150 → 筹码分散
        bars = mk_bars([50 + i for i in range(100)])
        r = chip_analysis(bars, float_shares=1e8, price=150.0)
        self.assertTrue(r["available"])
        self.assertEqual(r["level"], "无")
        self.assertGreater(r["width90"], 0.48)

    def test_missing_float_shares_unavailable(self):
        bars = mk_bars([10.0] * 60)
        r = chip_analysis(bars, float_shares=0, price=10.0)
        self.assertFalse(r["available"])
        self.assertIn("reason", r)

    def test_too_few_bars_unavailable(self):
        r = chip_analysis(mk_bars([10.0] * 10), float_shares=1e8, price=10.0)
        self.assertFalse(r["available"])


class LevelTests(unittest.TestCase):
    @staticmethod
    def _triangle(n):
        out = []
        for i in range(n):
            tri = abs(((i % 20) - 10) / 10)
            out.append(8 + 4 * (1 - tri))
        return out

    def test_support_resistance_from_contact_points(self):
        closes = self._triangle(105)  # 末价≈10，谷≈8，峰≈12
        bars = mk_bars(closes)
        r = detect_levels(bars, price=10.0)
        self.assertTrue(r["available"])
        sup = r["short"]["support"]
        res = r["short"]["resistance"]
        self.assertTrue(sup and res)
        self.assertLess(sup[0]["price"], 10.0)
        self.assertGreater(res[0]["price"], 10.0)
        self.assertAlmostEqual(sup[0]["price"], 7.96, delta=0.5)
        self.assertAlmostEqual(res[0]["price"], 12.06, delta=0.5)
        self.assertGreaterEqual(sup[0]["touches"], 2)
        # 中期回看更久，接触点不少于短期
        self.assertGreaterEqual(
            r["mid"]["resistance"][0]["touches"], r["short"]["resistance"][0]["touches"])

    def test_insufficient_bars(self):
        r = detect_levels(mk_bars([10.0] * 20), price=10.0)
        self.assertFalse(r["available"])


class SignalTests(unittest.TestCase):
    @staticmethod
    def _decline_then_recover():
        closes = [100 * (0.992 ** i) for i in range(80)]
        c = closes[-1]
        for i in range(40):
            c *= 1.01
            closes.append(c)
        vols = [10000.0] * 80 + [10000 + i * 500 for i in range(40)]
        return mk_bars(closes, vols)

    def test_sixteen_signals_with_times(self):
        bars = self._decline_then_recover()
        sigs = detect_signals(bars)
        self.assertEqual(len(sigs), 16)
        expected = {
            "macd_buy": "buy", "macd_sell": "sell", "kdj_buy": "buy", "kdj_sell": "sell",
            "rsi_buy": "buy", "rsi_sell": "sell", "ma_buy": "buy", "ma_sell": "sell",
            "boll_buy": "buy", "boll_sell": "sell", "bull_align": "buy", "bear_align": "sell",
            "red_three": "buy", "black_three": "sell", "vol_bull": "buy", "vol_bear": "sell",
        }
        self.assertEqual({s["key"] for s in sigs}, set(expected))
        n = len(bars)
        for s in sigs:
            self.assertEqual(s["side"], expected[s["key"]])
            self.assertIn("now", s)
            if s["last_date"] is None:
                self.assertIsNone(s["days_ago"])
            else:
                self.assertGreaterEqual(s["days_ago"], 0)
                self.assertLess(s["days_ago"], n)

    def test_volume_state_current_today(self):
        bars = self._decline_then_recover()
        sigs = {s["key"]: s for s in detect_signals(bars)}
        # 恢复期量能递增 → 量多头当前生效且为今天
        self.assertTrue(sigs["vol_bull"]["now"])
        self.assertEqual(sigs["vol_bull"]["days_ago"], 0)
        self.assertTrue(sigs["vol_bull"]["active"])
        # 恢复期金叉应在近40个交易日内出现
        self.assertIsNotNone(sigs["ma_buy"]["last_date"])
        self.assertLessEqual(sigs["ma_buy"]["days_ago"], 40)

    def test_too_few_bars_returns_empty(self):
        self.assertEqual(detect_signals(mk_bars([10.0] * 30)), [])


class StageTests(unittest.TestCase):
    @staticmethod
    def _index_by_date(bars):
        return {b["dt"]: i for i, b in enumerate(bars)}

    def _assert_valid_cycle(self, result, bars):
        changes = result["recent_changes"]
        idx = self._index_by_date(bars)
        for i, ch in enumerate(changes):
            fi, ti = STAGES.index(ch["from"]), STAGES.index(ch["to"])
            self.assertIn((ti - fi) % 6, (1, 5), "阶段只能相邻推进或回退")
            if i:
                gap = idx[ch["date"]] - idx[changes[i - 1]["date"]]
                self.assertGreaterEqual(gap, 5, "阶段切换间隔不得小于5根K线")

    def test_downtrend_starts_in_decline(self):
        bars = mk_bars([100 * (0.99 ** i) for i in range(100)])
        r = trend_stage(bars)
        self.assertTrue(r["available"])
        self.assertEqual(r["stage"], "下跌阶段")
        self._assert_valid_cycle(r, bars)

    def test_no_daily_flapping_on_sine(self):
        import math
        closes = [100 * (1 + 0.15 * math.sin(i / 15)) for i in range(240)]
        bars = mk_bars(closes)
        r = trend_stage(bars)
        changes = r["recent_changes"]
        if len(changes) >= 2:
            self._assert_valid_cycle(r, bars)

    def test_decline_then_recovery_leaves_decline(self):
        closes = [100 * (0.99 ** i) for i in range(100)]
        c = closes[-1]
        for _ in range(70):
            c *= 1.004
            closes.append(c)
        bars = mk_bars(closes)
        r = trend_stage(bars)
        self.assertNotEqual(r["stage"], "下跌阶段")
        self._assert_valid_cycle(r, bars)

    def test_too_few_bars(self):
        r = trend_stage(mk_bars([10.0] * 40))
        self.assertFalse(r["available"])


class BuildTests(unittest.TestCase):
    def test_empty_klines_unavailable(self):
        r = build_technical_structure([], float_shares=1e8)
        self.assertFalse(r["available"])
        self.assertIn("reason", r)

    def test_full_payload_contract(self):
        closes = [100 * (0.995 ** i) for i in range(70)] + \
                 [70 * (1.006 ** i) for i in range(50)]
        bars = mk_bars(closes)
        r = build_technical_structure(bars, float_shares=1e8, price=bars[-1]["close"])
        self.assertTrue(r["available"])
        for key in ("chip", "trend_stage", "levels", "signals", "methodology", "as_of"):
            self.assertIn(key, r)
        self.assertEqual(len(r["signals"]), 16)


class RouteTests(unittest.TestCase):
    def test_route_registered(self):
        from app.main import app
        paths = [getattr(rt, "path", "") for rt in app.routes]
        self.assertTrue(any(p.endswith("/{symbol}/technical-structure") for p in paths), paths)


if __name__ == "__main__":
    unittest.main()
