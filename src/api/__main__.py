"""Run the API with: ``python -m src.api`` (uvicorn).

- ``API_SERVER_ADDRESS`` (default 127.0.0.1)
- ``API_SERVER_PORT``    (default 8000)
- ``API_RELOAD=1``       to enable autoreload during development
"""
from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    host = (os.getenv("API_SERVER_ADDRESS") or "127.0.0.1").strip() or "127.0.0.1"
    port_raw = (os.getenv("API_SERVER_PORT") or "8000").strip()
    port = int(port_raw) if port_raw.isdigit() else 8000
    reload = (os.getenv("API_RELOAD") or "").strip().lower() in {"1", "true", "yes", "on"}

    uvicorn.run("src.api.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
