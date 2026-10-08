import asyncio
import unittest
from datetime import date, timedelta

from app.core.datasource.manager import DataSourceManager
from app.core.datasource.sina_source import SinaSource
from app.core.market.regime_service import _score_snapshot
from app.core.market.intraday_analyzer import _detect_t_signals_low_lag
from app.core.replay.engine import ReplayEngine, ReplayGateError


class MarketWorkspaceTests(unittest.TestCase):
    def test_empty_book_and_ticks_are_unavailable(self):
        manager = DataSourceManager.__new__(DataSourceManager)

        async def empty(method, *args):
            return {"order_book": {"bid": [], "ask": []}} if method == "get_order_book" else {"ticks": []}

        manager._call = empty
        book = asyncio.run(manager.get_order_book("SH600000"))
        ticks = asyncio.run(manager.get_ticks("SH600000"))
        self.assertIsNone(book["wei_bi"])
        self.assertIsNone(book["wei_cha"])
        self.assertIsNone(ticks["outer_pct"])
        self.assertFalse(ticks["side_data_available"])

    def test_current_bar_replaces_cached_bar(self):
        original = [{"dt": "2026-09-24", "close": 10}]
        updated = [{"dt": "2026-09-24", "close": 11}]
        self.assertEqual(DataSourceManager._merge(original, updated)[0]["close"], 11)

    def test_rotation_requires_genuine_sample(self):
        score = _score_snapshot({"total": 0, "sector_count": 12, "positive_sectors": None})
        self.assertFalse(score["available"]["rotation"])

    def test_effective_sector_method_uses_signed_net_flow(self):
        source = SinaSource()
        source._EM_SECTORFLOW_CACHE = [{"sector_name": "sample", "net_inflow": -100, "amount": 1000}]
        source._EM_SECTORFLOW_TS = __import__("time").time()
        rows = source.get_sector_money_flow()
        self.assertEqual(rows[0]["net_inflow"], -100)

    def test_sector_speed_exposes_turnover_not_net_flow(self):
        source = SinaSource()
        source._fljk_sectors = lambda: [{"name": "sample", "change_pct": 2,
                                         "amount": 1000, "leader_name": "leader", "count": 12}]
        row = source.get_sector_speed()[0]
        self.assertEqual(row["turnover"], 1000)
        self.assertNotIn("net_inflow", row)

    def test_replay_does_not_relabel_current_data_as_history(self):
        engine = ReplayEngine.__new__(ReplayEngine)
        with self.assertRaises(ReplayGateError):
            asyncio.run(engine.resolve_target(date.today() - timedelta(days=8)))
        with self.assertRaises(ReplayGateError):
            asyncio.run(engine.resolve_target(date.today() + timedelta(days=2)))

    def test_t_shape_uses_confirmation_price(self):
        prices = [100, 99.7, 99.1, 99.4, 99.8] + [99.8] * 8
        bars = [{"time": f"09:{30 + i:02d}", "price": p, "vol_ratio": 2,
                 "rsi": 30, "vwap_dev": -1} for i, p in enumerate(prices)]
        signals = _detect_t_signals_low_lag(bars, 100, {"near_support": True})
        self.assertTrue(signals)
        self.assertEqual(signals[0]["pivot_price"], 99.1)
        self.assertEqual(signals[0]["confirm_price"], 99.8)
        self.assertNotEqual(signals[0]["pivot_time"], signals[0]["time"])


if __name__ == "__main__":
    unittest.main()
