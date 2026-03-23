#!/usr/bin/env python3
"""应用入口 - 简化版。"""

import uvicorn
from app.config import get_settings

if __name__ == "__main__":
    settings = get_settings()

    # debug 模式下开 reload，但 reload=True 时不能指定 workers
    workers = settings.api_workers if not settings.api_debug else 1

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
        workers=workers,
        log_level=settings.log_level.lower(),
        access_log=True,
    )
