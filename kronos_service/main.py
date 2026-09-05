"""Standalone local Kronos microservice entry point.

Run from the project root with ``python kronos_service/main.py``.
All Kronos source code and model files are rooted in this directory.
"""

import os
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent
os.environ.setdefault("KRONOS_SERVICE_ROOT", str(SERVICE_ROOT))
os.environ.setdefault("KRONOS_SOURCE_DIR", str(SERVICE_ROOT))
os.environ.setdefault("KRONOS_MODEL_ROOT", str(SERVICE_ROOT))

from service import app, SERVICE_PORT, LOG_LEVEL  # noqa: E402


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("KRONOS_HOST", "127.0.0.1"),
        port=SERVICE_PORT,
        log_level=LOG_LEVEL.lower(),
    )
