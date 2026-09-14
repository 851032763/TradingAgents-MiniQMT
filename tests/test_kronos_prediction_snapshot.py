"""Regression coverage for the API-to-Kronos prediction contract."""

from __future__ import annotations

from types import SimpleNamespace

from api.main import KronosPredictionRunRequest, _run_kronos_prediction_snapshot


def test_snapshot_forwards_requested_horizon_and_dates_actual_output(monkeypatch):
    """A non-default horizon must not silently become the service default."""

    candles = [
        {
            "date": f"2026-09-{day:02d}",
            "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5,
            "volume": 100.0, "amount": 1050.0,
        }
        for day in range(1, 16)
    ]
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "api.main.get_kline",
        lambda **_kwargs: SimpleNamespace(candles=candles, source="miniqmt"),
    )

    def fake_kronos(path, *, method="GET", payload=None):
        if path == "/health":
            return {"model": "base", "device": "cpu"}
        captured.update(payload or {})
        return {
            "success": True,
            "predictions": [
                {"open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 100.0, "amount": 1000.0}
                for _ in range(3)
            ],
            "inference_time_ms": 1.0,
        }

    monkeypatch.setattr("api.main._kronos_service_request", fake_kronos)
    request = KronosPredictionRunRequest(symbol="000001.SZ", lookback=12, pred_len=3)

    snapshot = _run_kronos_prediction_snapshot(request, SimpleNamespace())

    assert captured["pred_len"] == 3
    assert len(snapshot["predictions"]) == 3
    assert len(snapshot["forecast_dates"]) == 3
    assert snapshot["parameter_snapshot"] == {
        "snapshot_format": 1,
        "request": {
            "symbol": "000001.SZ", "frequency": "D", "market_period": "1d",
            "lookback": 12, "pred_len": 3, "temperature": 1.0, "top_p": 0.9,
            "sample_count": 1, "model_key": "base",
        },
        "market_data": {
            "query_start_date": snapshot["parameter_snapshot"]["market_data"]["query_start_date"],
            "query_end_date": snapshot["parameter_snapshot"]["market_data"]["query_end_date"],
            "source": "miniqmt", "valid_candle_count": 15,
            "history_start_date": "2026-09-04", "history_end_date": "2026-09-15",
            "history_candle_count": 12,
        },
        "execution": {
            "model_loaded": "base", "device": "cpu", "inference_time_ms": 1.0,
            "prediction_candle_count": 3, "forecast_start_date": "2026-09-16",
            "forecast_end_date": "2026-09-18", "trading_calendar": "cn_a_share",
        },
    }
