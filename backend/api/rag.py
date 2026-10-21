"""知识库接口（BACKEND.md 第 13 章）。全部仅 root —— 知识库是公共资产。

`TPA_RAG_ENABLED=false` 时本组全部返回 503 RAG_DISABLED。
"""

from __future__ import annotations

import logging
import time
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from ..config import settings
from ..deps import DbSession, RootUser
from ..errors import ApiError, ok
from ..schemas import RagUrlRequest, rag_document_item
from ..services.rag_service import (
    MAX_FILE_BYTES,
    assert_enabled,
    check_extension,
    check_magic,
    rag_service,
    safe_filename,
)

logger = logging.getLogger("tpa.api.rag")

router = APIRouter(prefix="/rag", tags=["rag"])

CHUNK = 1024 * 1024


async def _read_upload(upload: UploadFile) -> bytes:
    """**流式读取时边读边计数**，不先全读进内存。"""
    total = 0
    pieces: list[bytes] = []
    while True:
        piece = await upload.read(CHUNK)
        if not piece:
            break
        total += len(piece)
        if total > MAX_FILE_BYTES:
            raise ApiError("RAG_FILE_TOO_LARGE", "文件不能超过 20 MB", 400)
        pieces.append(piece)
    if total == 0:
        raise ApiError("INVALID_ARGUMENT", "文件是空的", 400)
    return b"".join(pieces)


def _assert_magic(ext: str, data: bytes) -> None:
    head = data[:8]
    decodable = True
    if ext in {"md", "txt", "csv"}:
        decodable = False
        for encoding in ("utf-8", "utf-8-sig", "gbk"):
            try:
                data.decode(encoding)
                decodable = True
                break
            except UnicodeDecodeError:
                continue
    check_magic(ext, head, decodable)


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    user: RootUser,
    db: DbSession,
    file: Annotated[UploadFile, File(description="pdf/docx/md/txt/csv，≤20 MB")],
    title: Annotated[str | None, Form()] = None,
):
    """同步解析、分块、嵌入、入库，等 5–30 秒直接返回结果。"""
    assert_enabled()

    original = file.filename or "upload"
    ext = check_extension(original)
    data = await _read_upload(file)
    _assert_magic(ext, data)

    name = safe_filename(original)
    result = await rag_service.ingest_file(
        db,
        user=user,
        filename=name,
        title=(title or "").strip() or None,
        data=data,
    )
    return ok(result)


@router.post("/documents/from-url", status_code=status.HTTP_201_CREATED)
async def upload_from_url(payload: RagUrlRequest, user: RootUser, db: DbSession):
    """抓网页正文入库，用于跟踪"景区最新公告""交通新规"这类会变的信息。"""
    assert_enabled()
    result = await rag_service.ingest_url(
        db,
        user=user,
        url=payload.url.strip(),
        title=(payload.title or "").strip() or None,
    )
    return ok(result)


@router.get("/documents")
async def list_documents(user: RootUser, db: DbSession):
    """按 created_at 倒序，不分页。"""
    assert_enabled()
    documents = await rag_service.list_documents(db)
    return ok({"items": [rag_document_item(doc) for doc in documents]})


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, user: RootUser, db: DbSession):
    """删文档、其 Chroma 向量、磁盘文件（顺序保证可重入）。"""
    assert_enabled()
    await rag_service.delete_document(db, document_id)
    return ok({"deleted": True})


@router.get("/search")
async def search(
    user: RootUser,
    db: DbSession,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    top_k: Annotated[int | None, Query(ge=1, le=20)] = None,
):
    """检索调试接口：能区分"检索不到"和"检索到了但模型没用"。"""
    assert_enabled()
    query = (q or "").strip()
    if not query:
        raise ApiError("INVALID_ARGUMENT", "q 不能为空", 400)

    started = time.perf_counter()
    hits = await rag_service.search(db, query, top_k or settings.rag_top_k)
    return ok(
        {
            "query": query,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "hits": hits,
        }
    )
