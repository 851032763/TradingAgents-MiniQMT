"""Local MiniQMT cache synchronization and inspection.

The MiniQMT terminal owns the physical cache.  This service only orchestrates
xtdata download calls and persists a small, human-readable manifest so the web
UI can report progress and the last successful coverage after a server restart.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

import pandas as pd

from tradingagents.dataflows.providers.cn_miniqmt_provider import CnMiniQMTProvider


logger = logging.getLogger(__name__)

DATA_TYPES: dict[str, dict[str, str]] = {
    "market": {"label": "行情缓存", "detail": "日线、1 分钟、5 分钟 K 线"},
    "financial": {"label": "财务报表与指标", "detail": "三大报表、每股指标"},
    "capital_holder": {"label": "股本与股东", "detail": "股本、股东户数、前十大股东"},
    "instrument": {"label": "证券基础信息", "detail": "证券与板块基础资料"},
    "etf": {"label": "ETF 专项数据", "detail": "ETF 基础资料与成分相关缓存"},
}
DEFAULT_DATA_TYPES = list(DATA_TYPES)
FINANCIAL_TABLES = ["Balance", "Income", "CashFlow", "PershareIndex"]
# MiniQMT table names are case-sensitive (see xtdata.get_financial_data docs).
CAPITAL_HOLDER_TABLES = ["Capital", "HolderNum", "Top10Holder", "Top10FlowHolder"]
_STATE_PATH = Path(__file__).resolve().parents[2] / "data" / "miniqmt_sync_state.json"
_INSPECTION_BATCH_SIZE = 100
_PROGRESS_SAVE_BATCH_SIZE = 50
_INVENTORY_VERSION = 2


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _compact(date: datetime) -> str:
    return date.strftime("%Y%m%d")


class MiniQMTSyncService:
    """Serializes downloads because xtdata's download client is not re-entrant."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="miniqmt-sync")
        self._state = self._load_state()

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "status": "idle",
            "started_at": None,
            "finished_at": None,
            "message": "尚未发起同步",
            "progress": {"completed": 0, "total": 0, "current": None},
            "selected_types": [],
            "errors": [],
            "statistics": {},
            "symbols": {},
            "inventory_completed_at": None,
            "inventory_version": 0,
        }

    def _load_state(self) -> dict[str, Any]:
        try:
            loaded = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state = {**self._empty_state(), **loaded}
                if state.get("inventory_version") != _INVENTORY_VERSION:
                    state["inventory_completed_at"] = None
                    state["inventory_version"] = 0
                if state.get("status") in {"running", "inspecting"}:
                    state.update({
                        "status": "idle",
                        "finished_at": _now(),
                        "message": "服务重启前的数据任务已中断，将重新盘点本地缓存",
                    })
                return state
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("Could not read MiniQMT sync state: %s", exc)
        return self._empty_state()

    def _save_state_locked(self) -> None:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = _STATE_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(_STATE_PATH)

    def _snapshot_locked(self, symbol: str | None = None) -> dict[str, Any]:
        # A running sync can contain thousands of per-security entries. Only
        # copy the summary fields needed by the status page; copying the whole
        # manifest on every poll made refresh requests appear to hang.
        state = {
            key: json.loads(json.dumps(value, ensure_ascii=False))
            for key, value in self._state.items()
            if key != "symbols"
        }
        state["data_types"] = [
            {"key": key, **meta, "statistics": state.get("statistics", {}).get(key, {})}
            for key, meta in DATA_TYPES.items()
        ]
        if symbol:
            normalized = CnMiniQMTProvider._normalize_symbol(symbol)
            state["selected_symbol"] = self._inspect_symbol(
                normalized,
                self._state.get("symbols", {}).get(normalized, {}),
            )
        return state

    def get_status(self, symbol: str | None = None) -> dict[str, Any]:
        # The manifest only records downloads initiated from this application.
        # Start a read-only inventory so existing MiniQMT cache is visible too.
        self.inspect_local_cache()
        with self._lock:
            return self._snapshot_locked(symbol)

    def inspect_local_cache(self) -> dict[str, Any]:
        """Queue a read-only inventory of cache MiniQMT already owns."""
        with self._lock:
            if self._state.get("status") in {"running", "inspecting"}:
                return self._snapshot_locked()
            if self._state.get("inventory_completed_at"):
                return self._snapshot_locked()
            self._state.update({
                "status": "inspecting",
                "message": "正在盘点 MiniQMT 已有本地缓存（仅读取，不下载）",
                "progress": {"completed": 0, "total": 0, "current": None},
                "errors": [],
            })
            # Keep the first status request responsive. The full manifest can
            # be large; persist it once the read-only inventory completes.
            self._executor.submit(self._inspect_local_cache)
            return self._snapshot_locked()

    def start(self, selected_types: list[str] | None, symbols: list[str] | None = None) -> dict[str, Any]:
        types = list(dict.fromkeys(selected_types or DEFAULT_DATA_TYPES))
        invalid = [item for item in types if item not in DATA_TYPES]
        if invalid:
            raise ValueError(f"不支持的数据类型：{', '.join(invalid)}")
        normalized_symbols = list(dict.fromkeys(
            CnMiniQMTProvider._normalize_symbol(item) for item in (symbols or []) if item.strip()
        ))
        with self._lock:
            if self._state.get("status") in {"running", "inspecting"}:
                raise RuntimeError("已有 MiniQMT 数据任务正在运行")
            self._state = self._empty_state()
            self._state.update({
                "status": "running",
                "started_at": _now(),
                "message": "正在连接 MiniQMT 行情服务",
                "selected_types": types,
                "scope": "selected" if normalized_symbols else "market",
            })
            self._save_state_locked()
            self._executor.submit(self._run, types, normalized_symbols)
            return self._snapshot_locked()

    def _set_progress(
        self,
        *,
        completed: int | None = None,
        total: int | None = None,
        current: str | None = None,
        message: str | None = None,
        persist: bool = True,
    ) -> None:
        with self._lock:
            progress = self._state["progress"]
            if completed is not None:
                progress["completed"] = completed
            if total is not None:
                progress["total"] = total
            if current is not None:
                progress["current"] = current
            if message is not None:
                self._state["message"] = message
            if persist:
                self._save_state_locked()

    def _record_error(self, value: str) -> None:
        with self._lock:
            errors = self._state.setdefault("errors", [])
            if len(errors) < 50:
                errors.append(value)
            self._save_state_locked()

    @staticmethod
    def _call_if_available(xtdata: Any, name: str, *args: Any, **kwargs: Any) -> bool:
        method = getattr(xtdata, name, None)
        if not callable(method):
            return False
        method(*args, **kwargs)
        return True

    @staticmethod
    def _universe(xtdata: Any, explicit_symbols: list[str]) -> list[str]:
        if explicit_symbols:
            return explicit_symbols
        get_stocks = getattr(xtdata, "get_stock_list_in_sector", None)
        if not callable(get_stocks):
            raise RuntimeError("当前 MiniQMT 版本不支持读取证券范围，请在页面中指定股票后同步")
        result: list[str] = []
        # Sector labels vary slightly between MiniQMT releases. Duplicates are
        # removed so a terminal exposing overlapping sectors is still safe.
        for sector in ("沪深A股", "沪深ETF", "北交所", "沪深指数"):
            try:
                result.extend(str(code).upper() for code in (get_stocks(sector) or []))
            except Exception:
                continue
        valid = []
        for code in result:
            try:
                valid.append(CnMiniQMTProvider._normalize_symbol(code))
            except NotImplementedError:
                continue
        if not valid:
            raise RuntimeError("未从 MiniQMT 读取到证券范围，请确认行情服务已启动且已加载市场板块")
        return list(dict.fromkeys(valid))

    @staticmethod
    def _etf_universe(xtdata: Any, symbols: list[str], explicit_symbols: list[str]) -> list[str]:
        """Limit ETF work units to the ETF board, with a prefix fallback."""
        if not explicit_symbols:
            try:
                raw = getattr(xtdata, "get_stock_list_in_sector")("沪深ETF") or []
                etfs = {
                    CnMiniQMTProvider._normalize_symbol(str(code).upper())
                    for code in raw
                }
                return [symbol for symbol in symbols if symbol in etfs]
            except Exception:
                pass
        return [symbol for symbol in symbols if symbol.split(".", 1)[0].startswith(("51", "15", "56", "58"))]

    def _mark_type(
        self,
        symbol: str,
        data_type: str,
        start: str,
        end: str,
        status: str = "complete",
        note: str | None = None,
        *,
        persist: bool = True,
    ) -> None:
        def display_date(value: str) -> str:
            try:
                return datetime.strptime(value, "%Y%m%d").strftime("%Y-%m-%d")
            except ValueError:
                return value
        with self._lock:
            entry = self._state.setdefault("symbols", {}).setdefault(symbol, {"types": {}})
            entry["types"][data_type] = {
                "status": status, "start_date": display_date(start), "end_date": display_date(end),
                "updated_at": _now(), "note": note,
            }
            if persist:
                self._save_state_locked()

    @staticmethod
    def _should_persist_progress(completed: int, total: int) -> bool:
        return completed == total or completed % _PROGRESS_SAVE_BATCH_SIZE == 0

    def _mark_stage_symbols(
        self,
        symbols: list[str],
        data_type: str,
        start: str,
        end: str,
        completed: int,
        status: str,
    ) -> int:
        """Record a terminal-wide stage in batches without blocking status reads."""
        label = DATA_TYPES[data_type]["label"]
        for index, symbol in enumerate(symbols, start=1):
            self._mark_type(symbol, data_type, start, end, status, persist=False)
            completed += 1
            if index % _PROGRESS_SAVE_BATCH_SIZE == 0 or index == len(symbols):
                self._set_progress(
                    completed=completed,
                    current=f"{label} {index}/{len(symbols)}：{symbol}",
                    message=f"正在记录{label} {index}/{len(symbols)}",
                    persist=True,
                )
        return completed

    @staticmethod
    def _actual_market_bounds(xtdata: Any, symbol: str, fallback_start: str, fallback_end: str) -> tuple[str, str]:
        """Read the local daily cache after download and report real coverage."""
        try:
            raw = xtdata.get_market_data_ex(
                ["time", "open", "high", "low", "close", "volume"], [symbol],
                period="1d", start_time="20000101", end_time=fallback_end,
                dividend_type="front", fill_data=False,
            )
            frame = CnMiniQMTProvider._normalize_hist_df(CnMiniQMTProvider._as_frame(raw, symbol))
            if not frame.empty:
                return frame["Date"].min().strftime("%Y-%m-%d"), frame["Date"].max().strftime("%Y-%m-%d")
        except Exception:
            # The download itself succeeded; keep the requested interval when
            # a particular terminal build cannot read the cache back here.
            pass
        return datetime.strptime(fallback_start, "%Y%m%d").strftime("%Y-%m-%d"), datetime.strptime(fallback_end, "%Y%m%d").strftime("%Y-%m-%d")

    def _run(self, selected_types: list[str], explicit_symbols: list[str]) -> None:
        try:
            xtdata = CnMiniQMTProvider._xtdata()
            symbols = self._universe(xtdata, explicit_symbols)
            etf_symbols = self._etf_universe(xtdata, symbols, explicit_symbols)
            start = _compact(datetime.now() - timedelta(days=365 * 10))
            end = _compact(datetime.now())
            work_units = len(symbols) * sum(1 for item in selected_types if item in {"market", "financial", "capital_holder"})
            if "instrument" in selected_types:
                work_units += len(symbols)
            if "etf" in selected_types:
                work_units += len(etf_symbols)
            completed = 0
            self._set_progress(total=work_units, current=None, message=f"已载入 {len(symbols)} 个证券，开始下载")

            if "instrument" in selected_types:
                self._set_progress(
                    current="证券基础信息",
                    message="MiniQMT 正在更新证券基础信息与板块缓存；该接口不提供细粒度进度回调",
                )
                try:
                    supported = self._call_if_available(xtdata, "download_sector_data")
                    stage_status = "complete" if supported else "unsupported"
                    if not supported:
                        self._record_error("证券基础信息：当前 MiniQMT 版本未提供 download_sector_data")
                except Exception as exc:
                    supported = False
                    stage_status = "failed"
                    self._record_error(f"证券基础信息：{type(exc).__name__}: {exc}")
                completed = self._mark_stage_symbols(
                    symbols, "instrument", start, end, completed, stage_status,
                )

            if "etf" in selected_types:
                self._set_progress(
                    current="ETF 专项数据",
                    message=f"正在更新 {len(etf_symbols)} 个 ETF 专项缓存",
                )
                try:
                    supported = self._call_if_available(xtdata, "download_etf_info")
                    stage_status = "complete" if supported else "unsupported"
                    if not supported:
                        self._record_error("ETF 专项数据：当前 MiniQMT 版本未提供 download_etf_info")
                except Exception as exc:
                    supported = False
                    stage_status = "failed"
                    self._record_error(f"ETF 专项数据：{type(exc).__name__}: {exc}")
                completed = self._mark_stage_symbols(
                    etf_symbols, "etf", start, end, completed, stage_status,
                )

            for index, symbol in enumerate(symbols, start=1):
                if "market" in selected_types:
                    self._set_progress(current=symbol, message=f"正在同步行情 {index}/{len(symbols)}：{symbol}", persist=False)
                    try:
                        for period in ("1d", "1m", "5m"):
                            xtdata.download_history_data(symbol, period, start, end)
                        actual_start, actual_end = self._actual_market_bounds(xtdata, symbol, start, end)
                        self._mark_type(symbol, "market", actual_start, actual_end, persist=False)
                    except Exception as exc:
                        self._mark_type(symbol, "market", start, end, "failed", str(exc), persist=False)
                        self._record_error(f"{symbol} 行情：{type(exc).__name__}: {exc}")
                    completed += 1
                    self._set_progress(
                        completed=completed,
                        persist=self._should_persist_progress(completed, work_units),
                    )

                for data_type, tables in (("financial", FINANCIAL_TABLES), ("capital_holder", CAPITAL_HOLDER_TABLES)):
                    if data_type not in selected_types:
                        continue
                    self._set_progress(
                        current=symbol,
                        message=f"正在同步{DATA_TYPES[data_type]['label']} {index}/{len(symbols)}：{symbol}",
                        persist=False,
                    )
                    try:
                        supported = self._call_if_available(xtdata, "download_financial_data", [symbol], tables, start, end)
                        if not supported:
                            supported = self._call_if_available(xtdata, "download_financial_data2", [symbol], tables, start, end)
                        if not supported:
                            raise RuntimeError("当前 MiniQMT 版本未提供财务数据下载接口")
                        self._mark_type(symbol, data_type, start, end, persist=False)
                    except Exception as exc:
                        self._mark_type(symbol, data_type, start, end, "failed", str(exc), persist=False)
                        self._record_error(f"{symbol} {DATA_TYPES[data_type]['label']}：{type(exc).__name__}: {exc}")
                    completed += 1
                    self._set_progress(
                        completed=completed,
                        persist=self._should_persist_progress(completed, work_units),
                    )

            with self._lock:
                self._state["status"] = "completed"
                self._state["finished_at"] = _now()
                self._state["message"] = "同步完成" if not self._state["errors"] else "同步完成，部分数据未能下载"
                self._state["statistics"] = self._statistics_locked()
                self._save_state_locked()
        except Exception as exc:
            logger.exception("MiniQMT cache synchronization failed")
            with self._lock:
                self._state["status"] = "failed"
                self._state["finished_at"] = _now()
                self._state["message"] = f"同步失败：{exc}"
                self._state.setdefault("errors", []).append(str(exc))
                self._state["statistics"] = self._statistics_locked()
                self._save_state_locked()

    def _inspect_local_cache(self) -> None:
        """Find historical daily cache without making any download request."""
        try:
            xtdata = CnMiniQMTProvider._xtdata()
            symbols = self._universe(xtdata, [])
            discovered: dict[str, dict[str, Any]] = {}
            total = len(symbols)
            self._set_progress(total=total, current=None, message=f"正在读取 {total} 个证券的本地日线缓存", persist=False)

            for offset in range(0, total, _INSPECTION_BATCH_SIZE):
                batch = symbols[offset:offset + _INSPECTION_BATCH_SIZE]
                raw = xtdata.get_market_data_ex(
                    ["time"], batch, period="1d", start_time="20000101",
                    end_time=_compact(datetime.now()), fill_data=False,
                )
                for symbol in batch:
                    frame = CnMiniQMTProvider._as_frame(raw, symbol)
                    if frame.empty:
                        continue
                    times = self._cache_dates(frame)
                    valid = times.dropna()
                    if valid.empty:
                        continue
                    discovered[symbol] = {
                        "status": "complete",
                        "start_date": valid.min().strftime("%Y-%m-%d"),
                        "end_date": valid.max().strftime("%Y-%m-%d"),
                        "updated_at": _now(),
                        "note": "根据 MiniQMT 本地日线缓存盘点",
                    }
                completed = min(offset + len(batch), total)
                self._set_progress(completed=completed, current=batch[-1] if batch else None, persist=False)

            with self._lock:
                for symbol, market in discovered.items():
                    entry = self._state.setdefault("symbols", {}).setdefault(symbol, {"types": {}})
                    # The actual cache bounds take precedence over a prior
                    # requested download interval in the UI.
                    entry.setdefault("types", {})["market"] = market
                self._state["status"] = "idle"
                self._state["inventory_completed_at"] = _now()
                self._state["inventory_version"] = _INVENTORY_VERSION
                self._state["message"] = f"本地缓存盘点完成：发现 {len(discovered)} 个证券的日线数据"
                self._state["statistics"] = self._statistics_locked()
                self._save_state_locked()
        except Exception as exc:
            logger.exception("MiniQMT local cache inspection failed")
            with self._lock:
                self._state["status"] = "idle"
                self._state["message"] = f"本地缓存盘点未完成：{exc}"
                self._state.setdefault("errors", []).append(f"本地缓存盘点：{exc}")
                self._save_state_locked()

    def _statistics_locked(self) -> dict[str, Any]:
        output: dict[str, Any] = {}
        symbols = self._state.get("symbols", {})
        for data_type in DATA_TYPES:
            records = [item.get("types", {}).get(data_type) for item in symbols.values()]
            records = [item for item in records if item]
            completed = [item for item in records if item.get("status") == "complete"]
            starts = [item.get("start_date") for item in completed if item.get("start_date")]
            ends = [item.get("end_date") for item in completed if item.get("end_date")]
            output[data_type] = {
                "symbols": len(completed), "failed": sum(item.get("status") == "failed" for item in records),
                "start_date": min(starts) if starts else None, "end_date": max(ends) if ends else None,
                "updated_at": max((item.get("updated_at") or "" for item in completed), default=None),
            }
        return output

    @staticmethod
    def _cache_dates(frame: pd.DataFrame) -> pd.Series:
        values = frame.get("time", frame.index)
        # xtdata returns epoch milliseconds for cached bars. Without an
        # explicit unit pandas interprets them as nanoseconds (1970 dates).
        if pd.api.types.is_numeric_dtype(values):
            return pd.to_datetime(values, unit="ms", errors="coerce")
        return pd.to_datetime(values, errors="coerce")

    def _inspect_symbol(self, symbol: str, remembered: dict[str, Any]) -> dict[str, Any]:
        types = dict(remembered.get("types") or {})
        # The manifest tracks this screen's downloads. Probe categories that
        # are absent from it so older MiniQMT cache is visible per security.
        try:
            xtdata = CnMiniQMTProvider._xtdata()
            if "market" not in types:
                raw = xtdata.get_market_data_ex(["time"], [symbol], period="1d", start_time="20000101", end_time=_compact(datetime.now()))
                frame = CnMiniQMTProvider._as_frame(raw, symbol)
                if not frame.empty:
                    times = self._cache_dates(frame)
                    valid = times.dropna()
                    types["market"] = {
                        "status": "complete", "start_date": valid.min().strftime("%Y-%m-%d") if not valid.empty else None,
                        "end_date": valid.max().strftime("%Y-%m-%d") if not valid.empty else None,
                        "updated_at": None, "note": "根据本地日线缓存探测",
                    }
            if "instrument" not in types:
                detail = getattr(xtdata, "get_instrument_detail", lambda *_: None)(symbol)
                if detail:
                    types["instrument"] = {"status": "complete", "start_date": None, "end_date": None, "updated_at": None, "note": "本地基础信息可读取"}
            if "etf" not in types and symbol.startswith(("51", "15", "56", "58")):
                etf_info = getattr(xtdata, "get_etf_info", lambda *_: None)(symbol)
                if etf_info:
                    types["etf"] = {"status": "complete", "start_date": None, "end_date": None, "updated_at": None, "note": "本地 ETF 专项资料可读取"}
            for data_type, tables in (("financial", FINANCIAL_TABLES), ("capital_holder", CAPITAL_HOLDER_TABLES)):
                if data_type in types:
                    continue
                records = getattr(xtdata, "get_financial_data", lambda *_: {})([symbol], tables, "20000101", _compact(datetime.now()))
                frames = (records or {}).get(symbol, {}).values()
                if any(isinstance(frame, pd.DataFrame) and not frame.empty for frame in frames):
                    types[data_type] = {
                        "status": "complete", "start_date": None, "end_date": None, "updated_at": None,
                        "note": "根据 MiniQMT 本地财务缓存探测",
                    }
        except Exception as exc:
            types["connection"] = {"status": "unknown", "note": f"无法读取 MiniQMT 本地缓存：{exc}"}
        return {
            "symbol": symbol,
            "types": [{"key": key, **DATA_TYPES[key], **types.get(key, {"status": "missing"})} for key in DATA_TYPES],
            "complete": all(types.get(key, {}).get("status") == "complete" for key in (self._state.get("selected_types") or DEFAULT_DATA_TYPES)),
        }


_service: MiniQMTSyncService | None = None
_service_lock = Lock()


def get_miniqmt_sync_service() -> MiniQMTSyncService:
    global _service
    with _service_lock:
        if _service is None:
            _service = MiniQMTSyncService()
        return _service
