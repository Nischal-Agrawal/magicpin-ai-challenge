"""Vera Merchant AI Assistant — Root Application Entry Point."""

import uvicorn
from app.api import app, create_app
from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "bot:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )
