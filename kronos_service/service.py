#!/usr/bin/env python3
"""
Kronos Prediction Service - standalone local Python microservice
端口: 8101
功能: Kronos-small/base模型加载、K线预测、批量预测、模型切换
"""

import sys
import os
import logging
import time
import gc
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import pandas as pd
import torch

# Local microservice layout. The service can still fall back to Hugging Face
# IDs when a local model directory is not present, but defaults to local files.
SERVICE_ROOT = Path(os.environ.get("KRONOS_SERVICE_ROOT", Path(__file__).resolve().parent)).resolve()
KRONOS_DIR = Path(os.environ.get("KRONOS_SOURCE_DIR", SERVICE_ROOT)).resolve()
sys.path.insert(0, str(KRONOS_DIR))

MODEL_ROOT = Path(os.environ.get("KRONOS_MODEL_ROOT", SERVICE_ROOT)).resolve()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── 配置 ──
_BASE_DIR = MODEL_ROOT / "kronos-base"
_SMALL_DIR = MODEL_ROOT / "kronos-small"

# The downloaded folders in this project contain both artifacts. Base stores
# the model at its root and the tokenizer under tokenizer/. Small is inverted.
MODEL_REGISTRY = {
    "small": str(_SMALL_DIR / "tokenizer") if (_SMALL_DIR / "tokenizer" / "config.json").exists() else "NeoQuasar/Kronos-small",
    "base": str(_BASE_DIR) if (_BASE_DIR / "config.json").exists() else "NeoQuasar/Kronos-base",
}
TOKENIZER_REGISTRY = {
    "small": str(_SMALL_DIR) if (_SMALL_DIR / "config.json").exists() else "NeoQuasar/Kronos-Tokenizer-base",
    "base": str(_BASE_DIR / "tokenizer") if (_BASE_DIR / "tokenizer" / "config.json").exists() else "NeoQuasar/Kronos-Tokenizer-base",
}
DEFAULT_MODEL = os.environ.get("KRONOS_DEFAULT_MODEL", "base")
SERVICE_PORT = int(os.environ.get("KRONOS_SERVICE_PORT", "8101"))
LOG_LEVEL = os.environ.get("KRONOS_LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kronos_service")

# ── 模型全局变量 ──
_kronos_model = None
_kronos_tokenizer = None
_kronos_predictor = None
_device = None
_current_model_name = None
_model_loading = False


def load_model(model_key: str = None):
    """加载 Kronos 模型到自动选择的设备（CUDA 或 CPU）。"""
    global _kronos_model, _kronos_tokenizer, _kronos_predictor, _device, _current_model_name, _model_loading

    if _model_loading:
        raise HTTPException(status_code=503, detail="模型正在加载中，请稍后重试")

    model_key = model_key or DEFAULT_MODEL
    if model_key not in MODEL_REGISTRY:
        raise ValueError(f"未知模型: {model_key}, 可用模型: {list(MODEL_REGISTRY.keys())}")

    _model_loading = True
    model_name = MODEL_REGISTRY[model_key]

    try:
        from model import Kronos, KronosTokenizer, KronosPredictor

        _device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f"Using device: {_device}")

        # 如果已加载模型，先卸载
        if _kronos_model is not None:
            logger.info(f"Unloading previous model: {_current_model_name}")
            del _kronos_model, _kronos_predictor
            _kronos_model = None
            _kronos_predictor = None
            if _device.type == 'cuda':
                torch.cuda.empty_cache()
                gc.collect()
                logger.info("GPU cache cleared")

        tokenizer_name = TOKENIZER_REGISTRY[model_key]
        logger.info(f"Loading tokenizer from {tokenizer_name}...")
        _kronos_tokenizer = KronosTokenizer.from_pretrained(tokenizer_name)
        _kronos_tokenizer = _kronos_tokenizer.to(_device)
        _kronos_tokenizer.eval()
        logger.info("Tokenizer loaded!")

        logger.info(f"Loading model from {model_name}...")
        _kronos_model = Kronos.from_pretrained(model_name)
        _kronos_model = _kronos_model.to(_device)
        _kronos_model.eval()
        logger.info("Model loaded!")

        _kronos_predictor = KronosPredictor(
            _kronos_model, _kronos_tokenizer,
            max_context=512, device=_device
        )

        _current_model_name = model_key

        if _device.type == 'cuda':
            vram_mb = torch.cuda.memory_allocated() / 1024**2
            logger.info(f"GPU VRAM used: {vram_mb:.1f} MB")
        logger.info(f"Kronos Prediction Service ready with model: {model_key}!")
    finally:
        _model_loading = False


# ── Pydantic Models ──
class KlineDataPoint(BaseModel):
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float = 0.0


class PredictRequest(BaseModel):
    """单次预测请求"""
    klines: List[KlineDataPoint] = Field(..., min_length=10, max_length=512,
                                          description="历史K线数据 (OHLCVA)")
    pred_len: int = Field(default=60, ge=1, le=200, description="预测长度")
    temperature: float = Field(default=1.0, ge=0.1, le=5.0,
                               alias="T", description="采样温度")
    top_p: float = Field(default=0.9, ge=0.0, le=1.0,
                         description="Nucleus sampling概率")
    sample_count: int = Field(default=1, ge=1, le=5,
                              description="采样次数(取平均)")
    freq: str = Field(default="D", description="数据频率 (D/H/min)")


class PredictResponse(BaseModel):
    """预测响应"""
    success: bool
    predictions: Optional[List[Dict[str, float]]] = None
    lookback: int
    pred_len: int
    inference_time_ms: float
    vram_used_mb: Optional[float] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    model: str
    device: str
    vram_used_mb: Optional[float] = None
    vram_total_mb: Optional[float] = None


class ModelSwitchRequest(BaseModel):
    model_key: str = Field(..., description="模型标识: small 或 base")


class ModelInfoResponse(BaseModel):
    available_models: Dict[str, str]
    current_model: Optional[str]
    loading: bool


# ── FastAPI App ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Starting Kronos Prediction Service...")
    load_model()
    yield
    logger.info("Shutting down Kronos Prediction Service...")
    if _device and _device.type == 'cuda':
        torch.cuda.empty_cache()


app = FastAPI(
    title="Kronos Prediction Service",
    description="Kronos-small/base 金融K线序列预测服务",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

_cors_origins = [origin.strip() for origin in os.environ.get(
    "KRONOS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/models/info", response_model=ModelInfoResponse)
async def model_info():
    """获取模型信息"""
    return ModelInfoResponse(
        available_models={k: Path(v).name if Path(v).exists() else v.split("/")[-1]
                          for k, v in MODEL_REGISTRY.items()},
        current_model=_current_model_name,
        loading=_model_loading,
    )


@app.post("/models/switch")
async def model_switch(request: ModelSwitchRequest):
    """切换模型"""
    try:
        load_model(request.model_key)
        return {"success": True, "model": request.model_key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模型切换失败: {str(e)}")


@app.get("/health", response_model=HealthResponse)
async def health():
    """健康检查"""
    vram_mb = None
    vram_total_mb = None
    if _device and _device.type == 'cuda':
        vram_mb = round(torch.cuda.memory_allocated() / 1024**2, 1)
        vram_total_mb = round(torch.cuda.get_device_properties(0).total_memory / 1024**2, 1)

    return HealthResponse(
        status="ready" if _kronos_predictor else "loading",
        model=_current_model_name or "unknown",
        device=str(_device) if _device else "unknown",
        vram_used_mb=vram_mb,
        vram_total_mb=vram_total_mb,
    )


@app.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest):
    """预测接口"""
    if _kronos_predictor is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        # 构建DataFrame
        df = pd.DataFrame([k.model_dump() for k in request.klines])
        n = len(df)

        # 创建时间戳索引
        dates = pd.date_range('2000-01-01', periods=n, freq=request.freq)
        df.index = dates

        x_timestamp = df.index
        y_timestamp = pd.date_range(
            x_timestamp[-1] + pd.Timedelta(1, unit='D' if request.freq == 'D' else 'h'),
            periods=request.pred_len,
            freq=request.freq
        )

        # 推理计时
        t0 = time.time()
        pred_df = _kronos_predictor.predict(
            df=df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=request.pred_len,
            T=request.temperature,
            top_p=request.top_p,
            sample_count=request.sample_count,
            verbose=False,
        )
        inference_time = (time.time() - t0) * 1000

        # 转换为响应格式
        predictions = pred_df.to_dict(orient='records')

        vram_mb = None
        if _device and _device.type == 'cuda':
            torch.cuda.synchronize()
            vram_mb = round(torch.cuda.max_memory_allocated() / 1024**2, 1)
            torch.cuda.reset_peak_memory_stats()

        logger.info(f"Prediction done: {n} -> {request.pred_len} periods, "
                     f"{inference_time:.1f}ms")

        return PredictResponse(
            success=True,
            predictions=predictions,
            lookback=n,
            pred_len=request.pred_len,
            inference_time_ms=round(inference_time, 1),
            vram_used_mb=vram_mb,
        )

    except Exception as e:
        logger.error(f"Prediction error: {e}", exc_info=True)
        return PredictResponse(
            success=False,
            lookback=len(request.klines),
            pred_len=request.pred_len,
            inference_time_ms=0,
            error=str(e),
        )


@app.post("/predict/batch")
async def predict_batch(requests: List[PredictRequest]):
    """批量预测接口"""
    results = []
    for req in requests:
        result = await predict(req)
        results.append(result)
    return results


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "service:app",
        host="0.0.0.0",
        port=SERVICE_PORT,
        log_level=LOG_LEVEL.lower(),
    )
