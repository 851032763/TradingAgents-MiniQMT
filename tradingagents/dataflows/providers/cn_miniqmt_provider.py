"""MiniQMT (xtquant) provider for locally available China market data.

MiniQMT is intentionally imported lazily: ``xtquant`` is supplied by a local
MiniQMT installation and is not a package that should be installed from PyPI.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from stockstats import wrap

from .base import BaseMarketDataProvider
from ..trade_calendar import cn_market_phase, cn_no_data_reason, is_cn_trading_day, now_cn


logger = logging.getLogger(__name__)
_XT_DATA_IMPORT_LOGGED = False
_XT_DATA_CONNECTION_LOGGED = False
CN_TZ = ZoneInfo("Asia/Shanghai")


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
        global _XT_DATA_IMPORT_LOGGED, _XT_DATA_CONNECTION_LOGGED
        xtquant_path = os.getenv("MINIQMT_XTQUANT_PATH", "").strip()
        logger.info(
            "[MiniQMT] preparing xtquant: python=%s executable=%s configured_path=%r",
            sys.version.split()[0], sys.executable, xtquant_path or "<empty>",
        )
        if not xtquant_path:
            logger.error("[MiniQMT] MINIQMT_XTQUANT_PATH is empty; cannot load local xtquant")
        if xtquant_path and xtquant_path not in sys.path:
            # MiniQMT distributes xtquant with its desktop installation instead
            # of publishing it to PyPI. The configured directory is its parent.
            sys.path.insert(0, xtquant_path)
        try:
            from xtquant import xtdata  # type: ignore
            module_path = getattr(xtdata, "__file__", "<unknown>")
            if not _XT_DATA_IMPORT_LOGGED:
                logger.info("[MiniQMT] xtquant imported successfully: %s", module_path)
                _XT_DATA_IMPORT_LOGGED = True
            get_client = getattr(xtdata, "get_client", None)
            if callable(get_client):
                try:
                    client = get_client()
                    connected = getattr(client, "is_connected", lambda: True)()
                    if not connected:
                        raise RuntimeError("xtdata client returned is_connected=False")
                    if not _XT_DATA_CONNECTION_LOGGED:
                        logger.info("[MiniQMT] 行情服务已连接: historical/realtime requests are available")
                        _XT_DATA_CONNECTION_LOGGED = True
                except Exception as exc:
                    logger.exception("[MiniQMT] xtdata 行情服务连接失败: type=%s message=%s", type(exc).__name__, exc)
                    raise NotImplementedError(
                        f"cn_miniqmt行情服务连接失败: {type(exc).__name__}: {exc}"
                    ) from exc
            elif not _XT_DATA_CONNECTION_LOGGED:
                logger.warning("[MiniQMT] xtquant imported but get_client() is unavailable; connection will be checked by data request")
                _XT_DATA_CONNECTION_LOGGED = True
        except Exception as exc:
            logger.exception(
                "[MiniQMT] xtquant import failed: type=%s message=%s path=%r python=%s. "
                "This often means the xtquant native extension does not match the Python version.",
                type(exc).__name__, exc, xtquant_path, sys.version.split()[0],
            )
            raise NotImplementedError(
                "cn_miniqmt requires the xtquant package from a local MiniQMT installation. "
                f"Configured path={xtquant_path or '<empty>'}; Python={sys.version.split()[0]}."
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
    def _period(value: str) -> str:
        period = str(value).lower().strip()
        if period not in {"1m", "5m"}:
            raise ValueError(f"unsupported intraday period {value!r}; expected 1m or 5m")
        return period

    @staticmethod
    def _time_compact(value: str, end: bool = False) -> str:
        """Convert an ISO date/time into the format accepted by xtdata."""
        text = str(value).strip()
        formats = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")
        for fmt in formats:
            try:
                parsed = datetime.strptime(text, fmt)
                if fmt == "%Y-%m-%d" and end:
                    parsed = parsed.replace(hour=23, minute=59, second=59)
                return parsed.strftime("%Y%m%d%H%M%S")
            except ValueError:
                continue
        raise ValueError(f"invalid time {value!r}; expected YYYY-MM-DD or ISO datetime")

    @staticmethod
    def _auto_download_enabled() -> bool:
        return os.getenv("MINIQMT_AUTO_DOWNLOAD", "0").strip().lower() in {
            "1", "true", "yes", "on"
        }

    @staticmethod
    def _intraday_coverage_bounds(
        requested_start: pd.Timestamp,
        requested_end: pd.Timestamp,
        date_only: bool,
    ) -> tuple[pd.Timestamp, pd.Timestamp] | None:
        """Return the actual market-date bounds that minute data must cover."""
        if not date_only:
            return requested_start, requested_end

        start_date = requested_start.date()
        end_date = min(requested_end.date(), now_cn().date())
        if end_date < start_date:
            return None

        # Before today's open there cannot be a valid bar for today yet.
        if end_date == now_cn().date() and cn_market_phase() == "pre_open":
            end_date -= timedelta(days=1)

        first_date = start_date
        while first_date <= end_date and not is_cn_trading_day(first_date.strftime("%Y-%m-%d")):
            first_date += timedelta(days=1)

        last_date = end_date
        while last_date >= first_date and not is_cn_trading_day(last_date.strftime("%Y-%m-%d")):
            last_date -= timedelta(days=1)

        if first_date > last_date:
            return None
        return pd.Timestamp(first_date), pd.Timestamp(last_date)

    @classmethod
    def _intraday_data_covers(
        cls,
        df: pd.DataFrame,
        requested_start: pd.Timestamp,
        requested_end: pd.Timestamp,
        date_only: bool,
        minimum_bars: int,
    ) -> tuple[bool, tuple[pd.Timestamp, pd.Timestamp] | None]:
        bounds = cls._intraday_coverage_bounds(requested_start, requested_end, date_only)
        if df.empty or len(df) < minimum_bars or bounds is None:
            return False, bounds
        compare_dates = df["Date"].dt.normalize() if date_only else df["Date"]
        start_bound, end_bound = bounds
        covered = (
            compare_dates.min() <= start_bound and compare_dates.max() >= end_bound,
        )
        if not covered:
            return False, bounds

        # A same-day request after the close must include the afternoon
        # session. Date-only/minimum-bar checks otherwise accept 09:30-11:30
        # data as complete and never trigger MiniQMT's history refresh.
        if date_only and end_bound.date() == now_cn().date() and cn_market_phase() == "post_close":
            latest = df.loc[df["Date"].dt.normalize() == end_bound.normalize(), "Date"]
            if latest.empty or latest.max().time() < datetime.strptime("15:00", "%H:%M").time():
                return False, bounds
        return True, bounds

    def _download_if_enabled(self, code: str, start_date: str, end_date: str) -> None:
        if not self._auto_download_enabled():
            logger.info(
                "[MiniQMT] daily history missing for %s (%s..%s), auto download disabled",
                code, start_date, end_date,
            )
            return
        logger.info("[MiniQMT] downloading daily history: code=%s start=%s end=%s", code, start_date, end_date)
        try:
            self._xtdata().download_history_data(
                code, "1d", self._date_compact(start_date), self._date_compact(end_date)
            )
            logger.info("[MiniQMT] daily history download completed: code=%s", code)
        except Exception as exc:
            logger.exception("[MiniQMT] daily history download failed: code=%s", code)
            raise NotImplementedError(
                f"cn_miniqmt could not download daily history for {code}: {type(exc).__name__}: {exc}"
            ) from exc

    @staticmethod
    def _as_frame(result: Any, code: str) -> pd.DataFrame:
        if isinstance(result, dict):
            candidate = result.get(code)
            result = candidate if candidate is not None else result.get(code.upper())
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
            # Unix timestamps are UTC instants; the API contract uses China time.
            out["Date"] = (
                pd.to_datetime(numeric_dates, unit="ms", errors="coerce", utc=True)
                .dt.tz_convert(CN_TZ)
                .dt.tz_localize(None)
            )
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
        logger.info("[MiniQMT] reading daily history: code=%s start=%s end=%s", code, start_date, end_date)
        xtdata = self._xtdata()
        # xtdata treats the daily end_time as an exclusive boundary. Advance
        # it by one day so a request through today's date includes today's bar.
        query_end = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

        def fetch() -> pd.DataFrame:
            result = xtdata.get_market_data_ex(
                ["time", "open", "high", "low", "close", "volume", "amount"],
                [code],
                period="1d",
                start_time=self._date_compact(start_date),
                end_time=self._date_compact(query_end),
                dividend_type="front",
                fill_data=True,
            )
            frame = self._normalize_hist_df(self._as_frame(result, code))
            if frame.empty:
                return frame
            return frame[frame["Date"] < pd.Timestamp(query_end)].reset_index(drop=True)

        try:
            df = fetch()
        except Exception as exc:
            logger.exception("[MiniQMT] daily history read failed: code=%s", code)
            raise NotImplementedError(
                f"cn_miniqmt daily history request failed for {code}: {type(exc).__name__}: {exc}"
            ) from exc
        if df.empty and self._auto_download_enabled():
            self._download_if_enabled(code, start_date, query_end)
            df = fetch()
        df = self._merge_realtime_daily_bar(symbol, end_date, df)
        logger.info("[MiniQMT] daily history read completed: code=%s rows=%d", code, len(df))
        return df

    def _merge_realtime_daily_bar(
        self,
        symbol: str,
        end_date: str,
        history: pd.DataFrame,
    ) -> pd.DataFrame:
        """Overlay MiniQMT's latest full tick onto today's daily OHLCV bar.

        MiniQMT's downloaded daily cache can lag the live quote.  The analysis
        pipeline uses this daily frame to calculate technical and volume-price
        indicators, so the live quote has to be merged here rather than only in
        the chart API.
        """
        try:
            requested_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            return history

        current_time = now_cn()
        today = current_time.date()
        if requested_end != today or not is_cn_trading_day(today.strftime("%Y-%m-%d")):
            return history
        if cn_market_phase(current_time) in ("pre_open", "closed"):
            return history

        code = self._normalize_symbol(symbol)
        try:
            ticks = self._xtdata().get_full_tick([code])
            tick = ticks.get(code, {}) if isinstance(ticks, dict) else {}
            price = self._number(tick.get("lastPrice", tick.get("last_price")))
            if price is None:
                return history

            open_price = self._number(tick.get("open")) or price
            high_price = self._number(tick.get("high")) or price
            low_price = self._number(tick.get("low")) or price
            row = pd.DataFrame([{
                "Date": pd.Timestamp(today),
                "Open": open_price,
                "High": high_price,
                "Low": low_price,
                "Close": price,
                "Volume": self._number(tick.get("volume")),
                "Amount": self._number(tick.get("amount")),
            }])
            # A malformed tick should never replace a valid historical candle.
            if row[["Open", "High", "Low", "Close"]].isna().any(axis=None):
                return history

            merged = pd.concat([history, row], ignore_index=True)
            merged = merged.sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
            logger.info("[MiniQMT] overlaid live daily bar: code=%s date=%s", code, today)
            return merged.reset_index(drop=True)
        except Exception as exc:
            logger.warning(
                "[MiniQMT] live daily bar unavailable; using cached history: code=%s error=%s: %s",
                code,
                type(exc).__name__,
                exc,
            )
            return history

    def get_intraday_data(
        self, symbol: str, period: str, start_time: str, end_time: str,
    ) -> pd.DataFrame:
        """Read local MiniQMT minute bars and download missing history once.

        MiniQMT owns the local cache.  We intentionally re-read after a download
        so callers never receive fabricated or daily bars as minute data.
        """
        period = self._period(period)
        code = self._normalize_symbol(symbol)
        logger.info(
            "[MiniQMT] intraday request started: code=%s period=%s start=%s end=%s auto_download=%s",
            code, period, start_time, end_time, self._auto_download_enabled(),
        )
        xtdata = self._xtdata()
        start = self._time_compact(start_time)
        end = self._time_compact(end_time, end=True)

        def fetch() -> pd.DataFrame:
            result = xtdata.get_market_data_ex(
                ["time", "open", "high", "low", "close", "volume", "amount"],
                [code], period=period, start_time=start, end_time=end,
                dividend_type="front", fill_data=True,
            )
            return self._normalize_hist_df(self._as_frame(result, code))

        try:
            df = fetch()
        except Exception as exc:
            logger.exception("[MiniQMT] intraday local read failed: code=%s period=%s", code, period)
            raise NotImplementedError(
                f"cn_miniqmt {period} history request failed for {code}: {type(exc).__name__}: {exc}"
            ) from exc

        date_only = len(str(start_time)) <= 10 and len(str(end_time)) <= 10
        requested_start = pd.to_datetime(start_time)
        requested_end = pd.to_datetime(end_time) + (timedelta(days=1) - timedelta(seconds=1) if date_only else timedelta(0))
        minimum_bars = 60 if period == "1m" else 20
        enough, coverage_bounds = self._intraday_data_covers(
            df, requested_start, requested_end, date_only, minimum_bars,
        )
        logger.info(
            "[MiniQMT] intraday local read completed: code=%s period=%s rows=%d covered=%s expected_bounds=%s",
            code, period, len(df), enough, coverage_bounds,
        )
        if not enough:
            try:
                # xtdata has no portable `incrementally` keyword. Passing only
                # the missing range provides the same incremental behaviour.
                logger.info(
                    "[MiniQMT] intraday history download started: code=%s period=%s start=%s end=%s",
                    code, period, start_time, end_time,
                )
                xtdata.download_history_data(code, period, start, end)
                df = fetch()
                logger.info(
                    "[MiniQMT] intraday history download completed and re-read: code=%s period=%s rows=%d",
                    code, period, len(df),
                )
            except Exception as exc:
                logger.exception("[MiniQMT] intraday history download failed: code=%s period=%s", code, period)
                raise NotImplementedError(
                    f"cn_miniqmt {period} history download failed for {code}: {type(exc).__name__}: {exc}"
                ) from exc
        if df.empty:
            raise NotImplementedError(f"cn_miniqmt has no {period} history for {symbol}")
        df = df[(df["Date"] >= requested_start) & (df["Date"] <= requested_end)]
        enough, coverage_bounds = self._intraday_data_covers(
            df, requested_start, requested_end, date_only, minimum_bars,
        )
        if not enough:
            logger.error(
                "[MiniQMT] intraday data incomplete after download: code=%s period=%s rows=%d requested=%s..%s expected_bounds=%s",
                code, period, len(df), start_time, end_time, coverage_bounds,
            )
            raise NotImplementedError(f"cn_miniqmt {period} history is incomplete for {symbol}")
        logger.info("[MiniQMT] intraday request completed: code=%s period=%s rows=%d", code, period, len(df))
        return df.reset_index(drop=True)

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
        logger.info("[MiniQMT] realtime quote request started: symbols=%s codes=%s", symbols, codes)
        try:
            ticks = self._xtdata().get_full_tick(codes)
        except Exception as exc:
            logger.exception("[MiniQMT] realtime quote request failed: codes=%s", codes)
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
            logger.warning("[MiniQMT] realtime quote returned no data: codes=%s", codes)
            raise NotImplementedError("cn_miniqmt did not return realtime quotes")
        logger.info("[MiniQMT] realtime quote request completed: symbols=%s returned=%d", symbols, len(result))
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
