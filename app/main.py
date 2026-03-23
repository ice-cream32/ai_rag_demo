"""应用工厂 - LangChain Agent 后端服务"""

import logging
import time
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.api import chat, documents, rules, uploads
from app.openai_compat import router as openai_compat_router

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""

    application = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        debug=settings.api_debug,
        description="存储芯片知识库 AI - 基于 LangChain Agent + 阿里云百炼 API",
    )

    # CORS 中间件
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── API Key 鉴权中间件（仅当 API_KEY 非空时启用）────────────────
    if settings.api_key:
        @application.middleware("http")
        async def api_key_middleware(request: Request, call_next):
            """外网鉴权：请求头必须携带 X-API-Key"""
            skip_paths = {"/health", "/docs", "/openapi.json", "/redoc", "/v1/models", "/v1/chat/completions"}
            if request.url.path in skip_paths:
                return await call_next(request)
            key = request.headers.get("X-API-Key", "")
            if key != settings.api_key:
                logger.warning(
                    "API Key 校验失败 | client=%s | path=%s",
                    request.client.host if request.client else "unknown",
                    request.url.path,
                )
                return JSONResponse(
                    status_code=401,
                    content={"error": "Unauthorized", "detail": "Missing or invalid X-API-Key header"},
                )
            return await call_next(request)

    # ── 请求日志中间件 ───────────────────────────────────────────────
    @application.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        """记录每个 HTTP 请求到终端日志"""
        start_time = time.time()
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                "HTTP %s %s | status=%s | duration_ms=%.1f | client=%s",
                method, path, response.status_code, duration_ms, client_ip,
            )
            return response
        except Exception:
            duration_ms = (time.time() - start_time) * 1000
            logger.exception(
                "HTTP %s %s | status=500 | duration_ms=%.1f | client=%s",
                method, path, duration_ms, client_ip,
            )
            raise

    # ── 核心业务路由 ─────────────────────────────────────────────────
    application.include_router(chat.router, prefix="/api/v1", tags=["Chat"])
    application.include_router(documents.router, prefix="/api/v1", tags=["Documents"])
    application.include_router(rules.router, prefix="/api/v1", tags=["Rules"])
    application.include_router(uploads.router, prefix="/api/v1", tags=["Uploads"])
    if settings.openai_compat_enabled:
        application.include_router(openai_compat_router, prefix="/v1", tags=["OpenAI-Compatible"])

    @application.get("/health")
    async def health_check():
        """健康检查"""
        return {"status": "ok", "service": settings.api_title, "version": settings.api_version}

    @application.exception_handler(Exception)
    async def exception_handler(request, exc):
        logger.error(f"未处理的异常: {exc}")
        return JSONResponse(
            status_code=500,
            content={"error": "内部服务器错误", "detail": str(exc)}
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/v1/"):
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "message": "Invalid request payload",
                        "type": "invalid_request_error",
                        "param": None,
                        "code": "invalid_request",
                        "details": exc.errors(),
                    }
                },
            )
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    logger.info(f"FastAPI 应用已创建: {settings.api_title} v{settings.api_version}")
    return application


app = create_app()
