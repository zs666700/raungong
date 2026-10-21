"""错误码、响应信封与全局异常处理器（BACKEND.md 7.2–7.4）。"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("tpa.errors")

# 全部 22 个业务错误码 -> 默认 HTTP 状态（7.4 全表）
ERROR_STATUS: dict[str, int] = {
    "INVALID_ARGUMENT": 400,
    "AUTH_BAD_CREDENTIALS": 401,
    "AUTH_TOKEN_INVALID": 401,
    "AUTH_USERNAME_TAKEN": 409,
    "AUTH_WEAK_PASSWORD": 400,
    "AUTH_DISABLED": 403,
    "AUTH_REGISTER_CLOSED": 403,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "CONV_BUSY": 409,
    "MSG_EMPTY": 400,
    "LLM_FAILED": 500,
    "LLM_TIMEOUT": 504,
    "TOOL_NOT_FOUND": 404,
    "TOOL_FAILED": 502,
    "TOOL_UNAVAILABLE": 503,
    "RAG_DISABLED": 503,
    "RAG_FILE_TYPE": 400,
    "RAG_FILE_TOO_LARGE": 400,
    "RAG_EMPTY_TEXT": 400,
    "RAG_URL_BLOCKED": 400,
    "INTERNAL_ERROR": 500,
}


class ApiError(Exception):
    """业务异常。路由只管 raise，信封由全局处理器统一封装。"""

    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        self.code = code
        self.message = message
        self.status = status or ERROR_STATUS.get(code, 400)
        super().__init__(f"{code}: {message}")


def ok(data=None) -> dict:
    """成功信封。"""
    return {"ok": True, "data": data, "error": None}


def fail(code: str, message: str) -> dict:
    """失败信封。"""
    return {"ok": False, "data": None, "error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_request, exc: ApiError) -> JSONResponse:
        if exc.status >= 500:
            logger.error("ApiError %s: %s", exc.code, exc.message)
        return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request, exc: RequestValidationError) -> JSONResponse:
        detail = exc.errors()
        message = "参数不合法"
        if detail:
            first = detail[0]
            loc = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
            message = f"{loc or '参数'}: {first.get('msg', '参数不合法')}"
        return JSONResponse(status_code=400, content=fail("INVALID_ARGUMENT", message))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "AUTH_TOKEN_INVALID", 403: "FORBIDDEN", 404: "NOT_FOUND",
                409: "CONV_BUSY", 503: "TOOL_UNAVAILABLE"}.get(exc.status_code, "INTERNAL_ERROR")
        message = str(exc.detail) if exc.detail else "请求失败"
        return JSONResponse(status_code=exc.status_code, content=fail(code, message))

    @app.exception_handler(Exception)
    async def _unhandled(_request, exc: Exception) -> JSONResponse:
        logger.exception("未捕获异常: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content=fail("INTERNAL_ERROR", "服务内部错误"))
