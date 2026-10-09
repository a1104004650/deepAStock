import unittest

from app.core.event_study.engine import EventStudyEngine, _derived, _limit_threshold


def rows(prices, volumes=None, turnovers=None):
    volumes = volumes or [100] * len(prices)
    turnovers = turnovers or [None] * len(prices)
    return [
        {"date": __import__("datetime").date(2026, 1, i + 1), "open": price,
         "high": price * 1.01, "low": price * .99, "close": price,
         "volume": volumes[i], "turnover": turnovers[i]}
        for i, price in enumerate(prices)
    ]


class EventStudyTests(unittest.TestCase):
    def test_chinext_301_uses_twenty_percent_threshold(self):
        self.assertEqual(_limit_threshold("SZ301001"), .195)
        data = _derived(rows([10, 11]), "SZ301001", "sample")
        self.assertFalse(data[-1]["is_limit_up"])

    def test_three_consecutive_limit_ups(self):
        data = _derived(rows([10, 11, 12.1, 13.31, 13.5]), "SH600000", "sample")
        passed, detail, error = EventStudyEngine._evaluate(
            {"type": "limit_up_streak", "min": 3, "max": 3}, data, 3,
        )
        self.assertTrue(passed)
        self.assertEqual(detail["value"], 3)
        self.assertIsNone(error)

    def test_limit_pullback_with_strictly_shrinking_volume(self):
        data = _derived(
            rows([10, 11, 12.1, 11.8, 11.5], [100, 200, 300, 180, 120]),
            "SH600000", "sample",
        )
        passed, detail, error = EventStudyEngine._evaluate({
            "type": "post_limit_pullback", "streak_min": 1, "streak_max": 3,
            "days_min": 2, "days_max": 5, "shrinking_volume": True,
            "require_pullback": True, "max_drawdown_pct": 20,
        }, data, 4)
        self.assertTrue(passed)
        self.assertEqual(detail["value"]["days"], 2)
        self.assertEqual(detail["value"]["prior_streak"], 2)
        self.assertIsNone(error)

    def test_turnover_board_refuses_missing_field(self):
        data = _derived(rows([10, 11]), "SH600000", "sample")
        passed, _, error = EventStudyEngine._evaluate(
            {"type": "turnover_limit_up", "min": 8, "max": 35}, data, 1,
        )
        self.assertFalse(passed)
        self.assertIn("不可用", error)

    def test_forward_statistics_report_censoring_by_sample_count(self):
        events = [
            {"event_date": "2026-03-02", "forward": {"1": 10.0}, "relative": {"1": 5.0}},
            {"event_date": "2026-03-02", "forward": {"1": -2.0}, "relative": {"1": None}},
            {"event_date": "2026-03-03", "forward": {"1": None}, "relative": {"1": None}},
        ]
        stat = EventStudyEngine._statistics(events, [1])[0]
        self.assertEqual(stat["samples"], 2)
        self.assertEqual(stat["coverage_pct"], 66.7)
        self.assertEqual(stat["mean_pct"], 4.0)
        self.assertEqual(stat["benchmark_samples"], 1)

    def test_dual_weighting_and_date_cluster(self):
        events = [
            {"event_date": "2026-03-02", "forward": {"1": 10.0}, "relative": {"1": None}},
            {"event_date": "2026-03-02", "forward": {"1": 0.0}, "relative": {"1": None}},
            {"event_date": "2026-03-09", "forward": {"1": 4.0}, "relative": {"1": None}},
        ]
        stat = EventStudyEngine._statistics(events, [1])[0]
        self.assertEqual(stat["event_weighted"]["mean_pct"], 4.667)
        self.assertEqual(stat["date_weighted"]["days"], 2)
        self.assertEqual(stat["date_weighted"]["mean_pct"], 4.5)
        self.assertIsNotNone(stat["cluster_ci95_low_pct"])
        self.assertEqual(stat["stability"]["years_covered"], 1)

    def test_next_open_horizon_uses_next_day_open_to_close(self):
        import datetime
        series = [
            {"date": datetime.date(2026, 1, 1), "open": 10.0, "close": 10.0},
            {"date": datetime.date(2026, 1, 2), "open": 11.0, "close": 12.1},
            {"date": datetime.date(2026, 1, 5), "open": 12.2, "close": 13.0},
            {"date": datetime.date(2026, 1, 6), "open": 13.1, "close": 14.0},
        ]
        for i, row in enumerate(series):
            row.update({"high": row["close"] * 1.01, "low": row["close"] * .99, "volume": 100,
                        "turnover": None, "limit_streak": 0, "change": None, "amplitude": None,
                        "limit_threshold": .098, "is_limit_up": False, "ma5": None,
                        "volume_ma5": None, "index": i})
        event = EventStudyEngine._event("SH600000", "sample", series, 0, [1, 2], {}, [], "next_open")
        self.assertEqual(event["entry_price"], 11.0)
        self.assertAlmostEqual(event["forward"]["1"], round((12.1 / 11 - 1) * 100, 3))
        self.assertAlmostEqual(event["forward"]["2"], round((13.0 / 11 - 1) * 100, 3))
        bench = {
            datetime.date(2026, 1, 2): {"open": 4000.0, "close": 4100.0},
            datetime.date(2026, 1, 5): {"open": 4050.0, "close": 4040.0},
        }
        event = EventStudyEngine._event("SH600000", "sample", series, 0, [1], bench, [], "next_open")
        bench_ret = 4100.0 / 4000.0 - 1
        self.assertAlmostEqual(event["relative"]["1"],
                               round(((12.1 / 11 - 1) - bench_ret) * 100, 3))

    def test_event_close_basis_close_to_close(self):
        import datetime
        series = [
            {"date": datetime.date(2026, 1, 1), "open": 10.0, "close": 10.0},
            {"date": datetime.date(2026, 1, 2), "open": 11.0, "close": 12.1},
            {"date": datetime.date(2026, 1, 5), "open": 12.2, "close": 13.0},
        ]
        for i, row in enumerate(series):
            row.update({"high": row["close"] * 1.01, "low": row["close"] * .99, "volume": 100,
                        "turnover": None, "limit_streak": 0, "change": None, "amplitude": None,
                        "limit_threshold": .098, "is_limit_up": False, "ma5": None,
                        "volume_ma5": None, "index": i})
        event = EventStudyEngine._event("SH600000", "sample", series, 0, [1], {}, [], "event_close")
        self.assertEqual(event["entry_price"], 10.0)
        self.assertAlmostEqual(event["forward"]["1"], round((12.1 / 10 - 1) * 100, 3))

    def test_next_open_missing_entry_is_censored_not_fallback(self):
        import datetime
        series = [{
            "date": datetime.date(2026, 1, 1), "open": 10.0, "close": 10.0,
            "high": 10.1, "low": 9.9, "volume": 100, "turnover": None,
            "limit_streak": 0, "change": None, "amplitude": None,
            "limit_threshold": .098, "is_limit_up": False, "ma5": None,
            "volume_ma5": None, "index": 0,
        }]
        event = EventStudyEngine._event("SH600000", "sample", series, 0, [1], {}, [], "next_open")
        self.assertIsNone(event["entry_price"])
        self.assertIsNone(event["entry_date"])
        self.assertIsNone(event["forward"]["1"])
        self.assertEqual(event["entry_basis"], "next_open")


if __name__ == "__main__":
    unittest.main()
