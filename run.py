"""Run the reference API locally, following touchpoint-taxonomy's entry point."""

import os

import uvicorn


def main() -> None:
    """Start Uvicorn; reload is opt-in and the local default binds only to loopback."""
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "9031")),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        reload=os.getenv("RELOAD", "false").lower() in {"1", "true"},
    )


if __name__ == "__main__":
    main()
