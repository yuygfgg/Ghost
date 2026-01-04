import logging
import os
from collections.abc import Callable

try:
    from dotenv import load_dotenv as _load_dotenv
except Exception:  # pragma: no cover - optional dependency
    load_dotenv: Callable[..., object] | None = None
else:
    load_dotenv = _load_dotenv

if load_dotenv is not None:
    load_dotenv()

import uvicorn

from apps.api.main import app


def run() -> None:
    log_level = os.getenv("GHOST_API_LOG_LEVEL", "info").lower()
    logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    run()
