"""MiniQMT (xtquant) provider for locally available China market data.

MiniQMT is intentionally imported lazily: ``xtquant`` is supplied by a local
MiniQMT installation and is not a package that should be installed from PyPI.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from stockstats import wrap

from .base import BaseMarketDataProvider
from ..trade_calendar import cn_no_data_reason


class CnMiniQMTProvider(BaseMarketDataProvider):
    """A-share, ETF and index data served by a locally running MiniQMT client."""

    INDICATOR_DESCRIPTIONS = {
        "close_50_sma": "50 日均线（SMA）：中期趋势指标。",
        "close_200_sma": "200 日均线（SMA）：长期趋势基准。",
        "close_10_ema": "10 日指数均线（EMA）：短期响应更快。",
        "macd": "MACD：趋势与动量综合指标。",
        "macds": "MACD 信号线（Signal）。",
        "macdh": "MACD 柱状图（Histogram）。",
        "rsi": "RSI：衡量超买/超卖的动量指标。",
        "boll": "布林中轨（20 日均线）。",
        "boll_ub": "布林上轨。",
        "boll_lb": "布林下轨。",
        "atr": "ATR：真实波动幅度均值，用于波动与风控。",
        "vwma": "VWMA：成交量加权均线。",
        "mfi": "MFI：资金流量指标。",
    }

    @property
    def name(self) -> str:
        return "cn_miniqmt"

    @staticmethod
    def _xtdata():
        xtquant_path = os.getenv("MINIQMT_XTQUANT_PATH", "").strip()
        if xtquant_path and xtquant_path not in sys.path:
            # MiniQMT distributes xtquant with its desktop installation instead
            # of publishing it to PyPI. The configured directory is its parent.
            sys.path.insert(0, xtquant_path)
        try:
            from xtquant import xtdata  # type: ignore
        except ImportError as exc:
            raise NotImplementedError(
                "cn_miniqmt requires the xtquant package from a local MiniQMT installation. "
                "Set MINIQMT_XTQUANT_PATH to the directory containing the xtquant package."
            ) from exc
        return xtdata

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        value = symbol.strip().upper()
        if re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", value):
            return value
        if re.fullmatch(r"\d{6}", value):
            market = "SH" if value.startswith(("5", "6", "9")) else "SZ"
            return f"{value}.{market}"
        raise NotImplementedError(
            f"cn_miniqmt only supports China symbols such as 600519.SH, got: {symbol}"
        )

    @staticmethod
    def _date_compact(value: str) -> str:
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%Y%m%d")
        except ValueError as exc:
            raise ValueError(f"invalid date {value!r}; expected YYYY-MM-DD") from exc

    @staticmethod
    def _auto_download_enabled() -> bool:
        return os.getenv("MINIQMT_AUTO_DOWNLOAD", "0").strip().lower() in {
            "1", "true", "yes", "on"
        }

    def _download_if_enabled(self, code: str, start_date: str, end_date: str) -> None:
        if not self._auto_download_enabled():
            return
        try:
            self._xtdata().download_history_data(
                code, "1d", self._date_compact(start_date), self._date_compact(end_date)
            )
        except Exception as exc:
            raise NotImplementedError(
                f"cn_miniqmt could not download daily history for {code}: {type(exc).__name__}: {exc}"
            ) from exc

    @staticmethod
    def _as_frame(result: Any, code: str) -> pd.DataFrame:
        if isinstance(result, dict):
            result = result.get(code)
            if result is None:
                result = result.get(code.upper())
        if result is None:
            return pd.DataFrame()
        if not isinstance(result, pd.DataFrame):
            return pd.DataFrame(result)
        return result.copy()

    @staticmethod
    def _normalize_hist_df(raw: pd.DataFrame) -> pd.DataFrame:
        if raw is None or raw.empty:
            return pd.DataFrame()
        df = raw.copy()
        if "time" not in df.columns:
            df = df.reset_index()
        col_map = {
            "time": "Date", "datetime": "Date", "date": "Date", "index": "Date",
            "open": "Open", "high": "High", "low": "Low", "close": "Close",
            "volume": "Volume", "amount": "Amount",
        }
        df = df.rename(columns=col_map)
        required = ["Date", "Open", "High", "Low", "Close", "Volume"]
        if any(column not in df.columns for column in required):
            return pd.DataFrame()
        out = df[[column for column in [*required, "Amount"] if column in df.columns]].copy()
        date_values = out["Date"]
        numeric_dates = pd.to_numeric(date_values, errors="coerce")
        if pd.api.types.is_datetime64_any_dtype(date_values):
            out["Date"] = pd.to_datetime(date_values, errors="coerce")
        elif numeric_dates.notna().any() and numeric_dates.dropna().abs().median() > 10**11:
            # xtdata commonly exposes bar time as Unix milliseconds.
            out["Date"] = pd.to_datetime(numeric_dates, unit="ms", errors="coerce")
        elif numeric_dates.notna().any() and numeric_dates.dropna().abs().median() >= 10**7:
            out["Date"] = pd.to_datetime(date_values.astype(str), format="%Y%m%d", errors="coerce")
        else:
            out["Date"] = pd.to_datetime(date_values, errors="coerce")
        for column in ["Open", "High", "Low", "Close", "Volume", "Amount"]:
            if column in out.columns:
                out[column] = pd.to_numeric(out[column], errors="coerce")
        return (
            out.dropna(subset=required)
            .sort_values("Date")
            .drop_duplicates(subset=["Date"], keep="last")
            .reset_index(drop=True)
        )

    def _fetch_hist_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        code = self._normalize_symbol(symbol)
        xtdata = self._xtdata()

        def fetch() -> pd.DataFrame:
            result = xtdata.get_market_data_ex(
                ["time", "open", "high", "low", "close", "volume", "amount"],
                [code],
                period="1d",
                start_time=self._date_compact(start_date),
                end_time=self._date_compact(end_date),
                dividend_type="front",
                fill_data=True,
            )
            return self._normalize_hist_df(self._as_frame(result, code))

        try:
            df = fetch()
        except Exception as exc:
            raise NotImplementedError(
                f"cn_miniqmt daily history request failed for {code}: {type(exc).__name__}: {exc}"
            ) from exc
        if df.empty and self._auto_download_enabled():
            self._download_if_enabled(code, start_date, end_date)
            df = fetch()
        return df

    @staticmethod
    def _format_hist_csv(df: pd.DataFrame, symbol: str, start_date: str, end_date: str) -> str:
        if df.empty:
            return f"No MiniQMT data found for symbol '{symbol}' between {start_date} and {end_date}"
        out = df.copy()
        out["Dividends"] = 0.0
        out["Stock Splits"] = 0.0
        out["Date"] = out["Date"].dt.strftime("%Y-%m-%d")
        header = f"# Stock data for {symbol} from {start_date} to {end_date} (MiniQMT)\n"
        header += f"# Total records: {len(out)}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + out.to_csv(index=False)

    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> str:
        df = self._fetch_hist_df(symbol, start_date, end_date)
        if df.empty:
            raise NotImplementedError(
                f"cn_miniqmt has no local daily history for {symbol} between {start_date} and {end_date}"
            )
        return self._format_hist_csv(df, symbol, start_date, end_date)

    def get_indicators(
        self, symbol: str, indicator: str, curr_date: str, look_back_days: int
    ) -> str:
        if indicator not in self.INDICATOR_DESCRIPTIONS:
            raise ValueError(
                f"Indicator {indicator} is not supported. "
                f"Please choose from: {list(self.INDICATOR_DESCRIPTIONS.keys())}"
            )
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - timedelta(days=max(look_back_days, 260))
        df = self._fetch_hist_df(symbol, start_dt.strftime("%Y-%m-%d"), curr_date)
        if df.empty:
            raise NotImplementedError(
                f"cn_miniqmt has no local daily history for {symbol} indicator calculation"
            )
        ind_df = df.rename(
            columns={"Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
        )[["date", "open", "high", "low", "close", "volume"]].copy()
        values = wrap(ind_df)[indicator]
        values_by_date = {
            pd.to_datetime(day).strftime("%Y-%m-%d"): "N/A" if pd.isna(value) else str(value)
            for day, value in zip(ind_df["date"], values)
        }
        begin = curr_dt - timedelta(days=look_back_days)
        lines = []
        day = curr_dt
        while day >= begin:
            key = day.strftime("%Y-%m-%d")
            value = values_by_date.get(key, "N/A")
            lines.append(f"{key}: {cn_no_data_reason(key) if value == 'N/A' else value}")
            day -= timedelta(days=1)
        return (
            f"## {indicator} 指标值（{begin.strftime('%Y-%m-%d')} 至 {curr_date}，MiniQMT 行情计算）：\n\n"
            + "\n".join(lines)
            + "\n\n"
            + self.INDICATOR_DESCRIPTIONS[indicator]
        )

    def _financial_table(self, ticker: str, table: str, title: str, curr_date: str | None) -> str:
        code = self._normalize_symbol(ticker)
        end = curr_date or datetime.now().strftime("%Y-%m-%d")
        start = (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=365 * 8)).strftime("%Y-%m-%d")
        try:
            result = self._xtdata().get_financial_data(
                [code], [table], start_time=self._date_compact(start),
                end_time=self._date_compact(end), report_type="report_time",
            )
        except Exception as exc:
            raise NotImplementedError(
                f"cn_miniqmt financial request failed for {code}: {type(exc).__name__}: {exc}"
            ) from exc
        data = result.get(code, {}).get(table) if isinstance(result, dict) else None
        df = pd.DataFrame(data) if data is not None else pd.DataFrame()
        if df.empty:
            raise NotImplementedError(f"cn_miniqmt has no {title} data for {ticker}")
        return f"## {title} ({ticker}) - MiniQMT\n\n{df.head(12).iloc[:, :18].to_markdown(index=False)}"

    def get_fundamentals(self, ticker: str, curr_date: str = None) -> str:
        return self._financial_table(ticker, "PershareIndex", "公司关键指标", curr_date)

    def get_balance_sheet(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        return self._financial_table(ticker, "Balance", "资产负债表", curr_date)

    def get_cashflow(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        return self._financial_table(ticker, "CashFlow", "现金流量表", curr_date)

    def get_income_statement(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        return self._financial_table(ticker, "Income", "利润表", curr_date)

    def get_realtime_quotes(self, symbols: list[str]) -> str:
        pairs = [(symbol, self._normalize_symbol(symbol)) for symbol in symbols if symbol and symbol.strip()]
        if not pairs:
            return "{}"
        codes = [code for _, code in pairs]
        try:
            ticks = self._xtdata().get_full_tick(codes)
        except Exception as exc:
            raise NotImplementedError(
                f"cn_miniqmt realtime request failed: {type(exc).__name__}: {exc}"
            ) from exc
        result: dict[str, dict[str, Any]] = {}
        for original, code in pairs:
            tick = ticks.get(code, {}) if isinstance(ticks, dict) else {}
            if not tick:
                continue
            price = self._number(tick.get("lastPrice", tick.get("last_price")))
            previous = self._number(tick.get("lastClose", tick.get("last_close")))
            change = round(price - previous, 4) if price is not None and previous not in (None, 0) else None
            result[original] = {
                "price": price,
                "open": self._number(tick.get("open")),
                "high": self._number(tick.get("high")),
                "low": self._number(tick.get("low")),
                "previous_close": previous,
                "change": change,
                "change_pct": round(change / previous * 100, 4) if change is not None and previous else None,
                "volume": self._number(tick.get("volume")),
                "amount": self._number(tick.get("amount")),
                "quote_time": str(tick.get("time", "")) or None,
                "source": "miniqmt",
            }
        if not result:
            raise NotImplementedError("cn_miniqmt did not return realtime quotes")
        return json.dumps(result, ensure_ascii=False)

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            number = float(value)
            return number if pd.notna(number) else None
        except (TypeError, ValueError):
            return None

    def get_news(self, ticker: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError("cn_miniqmt does not provide news; use the next provider.")

    def get_global_news(self, curr_date: str, look_back_days: int = 7, limit: int = 50) -> str:
        raise NotImplementedError("cn_miniqmt does not provide global news; use the next provider.")

    def get_insider_transactions(self, symbol: str, curr_date: str = None) -> str:
        raise NotImplementedError("cn_miniqmt does not provide insider transactions; use the next provider.")
