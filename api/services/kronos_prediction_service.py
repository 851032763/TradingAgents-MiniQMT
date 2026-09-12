"""Persistence helpers for immutable, user-owned Kronos prediction snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.database import KronosPredictionRunDB


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def serialize(run: KronosPredictionRunDB, *, detail: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": run.id,
        "symbol": run.symbol,
        "security_name": run.security_name,
        "status": run.status,
        "error_message": run.error_message,
        "frequency": run.frequency,
        "lookback_requested": run.lookback_requested,
        "lookback_actual": run.lookback_actual,
        "pred_len": run.pred_len,
        "temperature": run.temperature,
        "top_p": run.top_p,
        "sample_count": run.sample_count,
        "model_key": run.model_key,
        "model_loaded": run.model_loaded,
        "device": run.device,
        "inference_time_ms": run.inference_time_ms,
        "history_start_date": run.history_start_date,
        "history_end_date": run.history_end_date,
        "market_data_source": run.market_data_source,
        "parameter_snapshot": run.parameter_snapshot or {},
        "summary": run.summary or {},
        "snapshot_version": run.snapshot_version,
        "created_at": _iso(run.created_at),
        "completed_at": _iso(run.completed_at),
    }
    if detail:
        data.update({
            "input_klines": run.input_klines or [],
            "forecast_dates": run.forecast_dates or [],
            "predictions": run.predictions or [],
        })
    return data


def create_running(
    db: Session,
    *,
    user_id: str,
    symbol: str,
    security_name: str,
    frequency: str,
    lookback_requested: int,
    pred_len: int,
    temperature: float,
    top_p: float,
    sample_count: int,
    model_key: str,
    parameter_snapshot: dict[str, Any],
) -> KronosPredictionRunDB:
    run = KronosPredictionRunDB(
        id=str(uuid4()),
        user_id=user_id,
        symbol=symbol,
        security_name=security_name,
        status="running",
        frequency=frequency,
        lookback_requested=lookback_requested,
        pred_len=pred_len,
        temperature=temperature,
        top_p=top_p,
        sample_count=sample_count,
        model_key=model_key,
        parameter_snapshot=parameter_snapshot,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def complete(
    db: Session,
    run: KronosPredictionRunDB,
    *,
    input_klines: list[dict[str, Any]],
    forecast_dates: list[str],
    predictions: list[dict[str, Any]],
    history_start_date: str,
    history_end_date: str,
    market_data_source: str | None,
    model_loaded: str | None,
    device: str | None,
    inference_time_ms: float | None,
    parameter_snapshot: dict[str, Any],
    summary: dict[str, Any],
) -> KronosPredictionRunDB:
    run.status = "completed"
    run.error_message = None
    run.lookback_actual = len(input_klines)
    run.input_klines = input_klines
    run.forecast_dates = forecast_dates
    run.predictions = predictions
    run.history_start_date = history_start_date
    run.history_end_date = history_end_date
    run.market_data_source = market_data_source
    run.model_loaded = model_loaded
    run.device = device
    run.inference_time_ms = inference_time_ms
    run.parameter_snapshot = parameter_snapshot
    run.summary = summary
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run


def fail(db: Session, run: KronosPredictionRunDB, message: str) -> KronosPredictionRunDB:
    run.status = "failed"
    run.error_message = message[:4000]
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run


def get(db: Session, run_id: str, user_id: str) -> KronosPredictionRunDB | None:
    return db.query(KronosPredictionRunDB).filter(
        KronosPredictionRunDB.id == run_id,
        KronosPredictionRunDB.user_id == user_id,
    ).first()


def list_runs(
    db: Session,
    *,
    user_id: str,
    symbol: str | None = None,
    status: str | None = None,
    frequency: str | None = None,
    model_key: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[int, list[KronosPredictionRunDB]]:
    query = db.query(KronosPredictionRunDB).filter(KronosPredictionRunDB.user_id == user_id)
    for column, value in (
        (KronosPredictionRunDB.symbol, symbol),
        (KronosPredictionRunDB.status, status),
        (KronosPredictionRunDB.frequency, frequency),
        (KronosPredictionRunDB.model_key, model_key),
    ):
        if value:
            query = query.filter(column == value)
    total = query.with_entities(func.count(KronosPredictionRunDB.id)).scalar() or 0
    runs = query.order_by(KronosPredictionRunDB.created_at.desc()).offset(skip).limit(limit).all()
    return int(total), runs


def delete(db: Session, run_id: str, user_id: str) -> bool:
    run = get(db, run_id, user_id)
    if not run:
        return False
    db.delete(run)
    db.commit()
    return True


def batch_delete(db: Session, run_ids: Iterable[str], user_id: str) -> int:
    ids = list(dict.fromkeys(item for item in run_ids if item))
    if not ids:
        raise ValueError("请选择至少一条预测记录")
    deleted = db.query(KronosPredictionRunDB).filter(
        KronosPredictionRunDB.user_id == user_id,
        KronosPredictionRunDB.id.in_(ids),
    ).delete(synchronize_session=False)
    db.commit()
    return int(deleted)
