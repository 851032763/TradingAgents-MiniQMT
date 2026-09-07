from __future__ import annotations

import re
from datetime import date, datetime, time
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas as pd

CN_TZ = ZoneInfo("Asia/Shanghai")


def now_cn() -> datetime:
    return datetime.now(CN_TZ)


def cn_today_str() -> str:
    return now_cn().date().strftime("%Y-%m-%d")


def _parse_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y-%m-%d").date()


@lru_cache(maxsize=1)
def _load_cn_trade_dates() -> tuple[list[date], set[date]]:
    try:
        import akshare as ak  # type: ignore

        df = ak.tool_trade_date_hist_sina()
        if df is None or df.empty or "trade_date" not in df.columns:
            raise ValueError("empty trade date table")
        dates = sorted(
            pd_dt.date()
            for pd_dt in pd.to_datetime(df["trade_date"], errors="coerce")
            if str(pd_dt) != "NaT"
        )
        return dates, set(dates)
    except Exception:
        # Fallback: no holiday calendar, only weekend rule.
        return [], set()


def is_cn_symbol(symbol: str) -> bool:
    s = symbol.strip().upper()
    return bool(re.match(r"^\d{6}(\.(SH|SZ|SS))?$", s))


def is_cn_trading_day(date_str: str) -> bool:
    d = _parse_date(date_str)
    dates, dates_set = _load_cn_trade_dates()
    if dates and dates[0] <= d <= dates[-1]:
        return d in dates_set
    return d.weekday() < 5


def previous_cn_trading_day(date_str: str) -> str:
    d = _parse_date(date_str)
    cur = d
    while True:
        cur = cur.fromordinal(cur.toordinal() - 1)
        if is_cn_trading_day(cur.strftime("%Y-%m-%d")):
            return cur.strftime("%Y-%m-%d")


def cn_market_phase(now: datetime | None = None) -> str:
    now_dt = now or now_cn()
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=CN_TZ)
    else:
        now_dt = now_dt.astimezone(CN_TZ)

    today = now_dt.date().strftime("%Y-%m-%d")
    if not is_cn_trading_day(today):
        return "closed"

    t = now_dt.time()
    if t < time(9, 30):
        return "pre_open"
    if time(9, 30) <= t < time(11, 30):
        return "in_session"
    if time(11, 30) <= t < time(13, 0):
        return "lunch_break"
    if time(13, 0) <= t < time(15, 0):
        return "in_session"
    return "post_close"


def latest_cn_data_date(end_date: str, now: datetime | None = None) -> str:
    """Return the latest market date that can have data for a request.

    Future and non-trading end dates roll back to the latest trading day.  A
    request made before today's open also rolls back because today's daily bar
    does not exist yet.
    """
    current = now or now_cn()
    if current.tzinfo is None:
        current = current.replace(tzinfo=CN_TZ)
    else:
        current = current.astimezone(CN_TZ)

    requested = min(_parse_date(end_date), current.date())
    requested_text = requested.strftime("%Y-%m-%d")
    if requested == current.date() and cn_market_phase(current) == "pre_open":
        return previous_cn_trading_day(requested_text)
    if is_cn_trading_day(requested_text):
        return requested_text
    return previous_cn_trading_day(requested_text)


def next_cn_trading_days(after_date: str, count: int) -> list[str]:
    """Return trading dates strictly after ``after_date`` in ascending order."""
    if count < 0:
        raise ValueError("count must be non-negative")
    current = _parse_date(after_date)
    result: list[str] = []
    while len(result) < count:
        current = current.fromordinal(current.toordinal() + 1)
        text = current.strftime("%Y-%m-%d")
        if is_cn_trading_day(text):
            result.append(text)
    return result


def cn_no_data_reason(date_str: str) -> str:
    if not is_cn_trading_day(date_str):
        return "N/A：非交易日（A股休市）"

    today = cn_today_str()
    if date_str == today:
        phase = cn_market_phase()
        if phase == "pre_open":
            return "N/A：今日尚未开盘"
        if phase in ("in_session", "lunch_break"):
            return "N/A：今日盘中，日线未收盘（可参考实时价）"
        if phase == "post_close":
            return "N/A：今日已收盘，数据源尚未更新"

    return "N/A：该交易日暂无数据（可能停牌或数据延迟）"
