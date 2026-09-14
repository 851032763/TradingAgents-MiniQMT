import os
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from tradingagents.dataflows.providers.cn_miniqmt_provider import CnMiniQMTProvider
from tradingagents.dataflows.trade_calendar import latest_cn_data_date, next_cn_trading_days


CN_TZ = ZoneInfo("Asia/Shanghai")


def _history_frame(last_date: str) -> pd.DataFrame:
    dates = pd.to_datetime(["2026-08-25", last_date])
    return pd.DataFrame(
        {
            "time": dates,
            "open": [1300.0, 1301.0],
            "high": [1310.0, 1311.0],
            "low": [1290.0, 1291.0],
            "close": [1304.0, 1302.8],
            "volume": [21000.0, 22000.0],
            "amount": [1.0, 2.0],
        }
    )


class MiniQMTDailyRefreshTests(unittest.TestCase):
    def test_latest_cn_data_date_rolls_weekend_back(self):
        now = datetime(2026, 9, 6, 12, 0, tzinfo=CN_TZ)
        with patch(
            "tradingagents.dataflows.trade_calendar._load_cn_trade_dates",
            return_value=([], set()),
        ):
            self.assertEqual(latest_cn_data_date("2026-09-06", now), "2026-09-04")

    def test_next_trading_days_use_exchange_calendar(self):
        calendar = pd.to_datetime(["2026-09-04", "2026-09-07", "2026-09-08"]).date.tolist()
        with patch(
            "tradingagents.dataflows.trade_calendar._load_cn_trade_dates",
            return_value=(calendar, set(calendar)),
        ):
            self.assertEqual(
                next_cn_trading_days("2026-09-04", 2),
                ["2026-09-07", "2026-09-08"],
            )

    def test_stale_nonempty_daily_cache_is_refreshed(self):
        class FakeXtData:
            def __init__(self):
                self.downloaded = False
                self.calls = []

            def get_market_data_ex(self, *args, **kwargs):
                last_date = "2026-09-04" if self.downloaded else "2026-08-26"
                return {"600519.SH": _history_frame(last_date)}

            def download_history_data(self, code, period, start, end):
                self.calls.append((code, period, start, end))
                self.downloaded = True

            def get_full_tick(self, codes):
                return {}

        fake = FakeXtData()
        provider = CnMiniQMTProvider()
        with (
            patch.dict(os.environ, {"MINIQMT_AUTO_DOWNLOAD": "1"}),
            patch.object(provider, "_xtdata", return_value=fake),
            patch(
                "tradingagents.dataflows.providers.cn_miniqmt_provider.latest_cn_data_date",
                return_value="2026-09-04",
            ),
        ):
            result = provider._fetch_hist_df("600519.SH", "2026-08-01", "2026-09-06")

        self.assertEqual(result["Date"].max().strftime("%Y-%m-%d"), "2026-09-04")
        self.assertEqual(fake.calls, [("600519.SH", "1d", "20260827", "20260907")])

    def test_weekend_quote_fills_latest_trading_day(self):
        quote_time = int(datetime(2026, 9, 4, 15, 31, tzinfo=CN_TZ).timestamp() * 1000)

        class FakeXtData:
            def get_full_tick(self, codes):
                return {
                    "600519.SH": {
                        "time": quote_time,
                        "lastPrice": 1330.0,
                        "open": 1295.88,
                        "high": 1338.86,
                        "low": 1295.6,
                        "volume": 45416.0,
                        "amount": 6022594700.0,
                    }
                }

        provider = CnMiniQMTProvider()
        history = CnMiniQMTProvider._normalize_hist_df(_history_frame("2026-08-26"))
        with (
            patch.object(provider, "_xtdata", return_value=FakeXtData()),
            patch(
                "tradingagents.dataflows.providers.cn_miniqmt_provider.latest_cn_data_date",
                return_value="2026-09-04",
            ),
        ):
            result = provider._merge_realtime_daily_bar("600519.SH", "2026-09-06", history)

        self.assertEqual(result.iloc[-1]["Date"].strftime("%Y-%m-%d"), "2026-09-04")
        self.assertEqual(result.iloc[-1]["Close"], 1330.0)


if __name__ == "__main__":
    unittest.main()
