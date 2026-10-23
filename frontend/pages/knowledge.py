"""知识库管理页（FRONTEND.md 10.1）。仅 root 可见。"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import ui

from ..api_client import ApiError, get_api
from ..components.dialogs import ConfirmDialog
from ..components.shell import AppShell
from ..state import human_error, require_root, toast_error
from ..theme import icon_svg
from ..ui_utils import badge, fmt_short, icon_button

logger = logging.getLogger("tpa.frontend.knowledge")


class KnowledgePage:
    def __init__(self, user: dict[str, Any]) -> None:
        self.user = user
        self.docs: list[dict[str, Any]] = []
        self.disabled = False
        self.loading = False
        self.search_seq = 0
        self.search_timer: Any = None
        self.table_slot: Any = None
        self.stats_slot: Any = None
        self.search_results: Any = None
        self.search_meta: Any = None
        self.search_input: Any = None
        self.upload_button: Any = None
        self.url_button: Any = None
        self.confirm = ConfirmDialog()
        self.upload_dialog: Any = None
        self.url_dialog: Any = None
        self.processing_dialog: Any = None
        self.preview_dialog: Any = None
        self.processing_text: Any = None
        self.processing_title: Any = None
        self.preview_body: Any = None
        self.preview_title: Any = None
        self.preview_meta: Any = None
        self.upload_title: Any = None
        self.uploader: Any = None
        self.url_input: Any = None
        self.url_title: Any = None

    async def build(self) -> None:
        shell = AppShell(self.user, "knowledge")
        main = shell.build()
        with main:
            shell.admin_topbar("知识库")
            with ui.element("div").classes("admin-scroll"):
                with ui.element("div").classes("admin-inner"):
                    self._head()
                    self.stats_slot = ui.element("div")
                    with ui.element("div").classes("tpa-table"):
                        with ui.element("div").classes("thead doc-head"):
                            ui.label("标题")
                            ui.label("类型")
                            ui.label("状态")
                            ui.label("块数")
                            ui.label("创建时间")
                            ui.label("操作")
                        self.table_slot = ui.element("div")
                    self._search_panel()
        self._dialogs()
        await self.refresh()

    def _head(self) -> None:
        with ui.element("div").classes("page-head"):
            with ui.element("div").classes("page-head-main"):
                ui.label("ADMIN / KNOWLEDGE").classes("page-kicker")
                ui.label("知识库").classes("page-title")
                ui.label(
                    "景区公告、交通新规、预约规则——上传后，助手回答时会引用这些资料，并在回复下方标出来源。"
                ).classes("page-sub")
            with ui.element("div").classes("page-actions"):
                self.url_button = ui.element("button").props("type=button").classes("btn-ghost")
                self.url_button.on("click", self._open_url)
                with self.url_button:
                    ui.html(icon_svg("link", 14))
                    ui.label("从网址添加")
                self.upload_button = ui.element("button").props("type=button").classes("btn-ink")
                self.upload_button.on("click", self._open_upload)
                with self.upload_button:
                    ui.html(icon_svg("upload", 14))
                    ui.label("上传文件")

    # ------------------------------------------------------------------ 列表
    async def refresh(self) -> None:
        if self.table_slot is None:
            return
        self._render_loading()
        try:
            data = await get_api().get("/api/v1/rag/documents")
        except ApiError as exc:
            if exc.code == "RAG_DISABLED":
                self.disabled = True
                self._set_actions_enabled(False)
                self._render_disabled()
                return
            if exc.code in {"FORBIDDEN", "AUTH_TOKEN_INVALID"}:
                toast_error(exc)
                return
            self._render_error(exc)
            return
        self.docs = list((data or {}).get("items") or [])
        self._render_stats()
        self._render_table()

    def _render_loading(self) -> None:
        self.table_slot.clear()
        with self.table_slot:
            for width in (72, 58, 64, 42, 54):
                with ui.element("div").classes("skeleton-row"):
                    ui.element("span").classes("skeleton-bar").style(f"width:{width}%")

    def _render_stats(self) -> None:
        ready = sum(1 for d in self.docs if d.get("status") == "ready")
        failed = sum(1 for d in self.docs if d.get("status") == "failed")
        chunks = sum(int(d.get("chunk_count") or 0) for d in self.docs)
        self.stats_slot.clear()
        with self.stats_slot:
            with ui.element("div").classes("stats"):
                for index, (value, label) in enumerate(
                    (
                        (len(self.docs), "份资料"),
                        (ready, "已入库"),
                        (failed, "失败"),
                        (chunks, "总块数"),
                    )
                ):
                    if index:
                        ui.element("div").classes("stat-div")
                    with ui.element("div").classes("stat"):
                        ui.label(str(value)).classes("stat-num")
                        ui.label(label).classes("stat-label")

    def _render_table(self) -> None:
        self.table_slot.clear()
        if not self.docs:
            self._render_empty()
            return
        with self.table_slot:
            for doc in self.docs:
                failed = str(doc.get("status")) == "failed"
                row = ui.element("div").classes("trow doc-row" + (" failed" if failed else ""))
                with row:
                    with ui.element("div").classes("cell"):
                        with ui.element("div").classes("cell-title"):
                            ui.label(str(doc.get("title") or "未命名资料"))
                            if failed:
                                ui.html(icon_svg("warn", 12)).style("color:var(--danger)")
                        sub = str(doc.get("filename") or "")
                        if failed and doc.get("error"):
                            ui.label(str(doc.get("error"))).classes("cell-sub error")
                        else:
                            ui.label(sub).classes("cell-sub")
                        kind_text = "网址" if doc.get("source_type") == "url" else "文件"
                        status_text = "可用" if doc.get("status") == "ready" else "失败"
                        ui.label(
                            f"{kind_text} · {status_text} · {doc.get('chunk_count') or 0} 块 · "
                            f"{fmt_short(doc.get('created_at'))}"
                        ).classes("mobile-meta")
                    with ui.element("div").classes("cell"):
                        kind = "网址" if doc.get("source_type") == "url" else "文件"
                        badge(kind)
                    with ui.element("div").classes("cell"):
                        if doc.get("status") == "ready":
                            badge("可用", "ok")
                        else:
                            badge("失败", "fail")
                    with ui.element("div").classes("cell cell-mono"):
                        ui.label(str(doc.get("chunk_count") or 0))
                    with ui.element("div").classes("cell cell-muted"):
                        ui.label(fmt_short(doc.get("created_at")))
                    with ui.element("div").classes("cell row-actions"):
                        icon_button(
                            "trash",
                            on_click=lambda _=None, d=doc: self._ask_delete(d),
                            tooltip="删除",
                            classes="mini",
                            size=15,
                        )

    def _render_empty(self) -> None:
        with self.table_slot:
            with ui.element("div").classes("empty-box"):
                ui.html(icon_svg("book", 34)).classes("empty-icon")
                ui.label("还没有文档").classes("empty-title")
                ui.label(
                    "上传景区公告、交通新规等资料，助手回答时会引用它们，并在回复下方标注来源。"
                ).classes("empty-text")
                with ui.element("div").classes("empty-actions"):
                    upload = ui.element("button").props("type=button").classes("btn-ink")
                    upload.on("click", self._open_upload)
                    with upload:
                        ui.html(icon_svg("upload", 14))
                        ui.label("上传第一份资料")

    def _render_error(self, exc: ApiError) -> None:
        self.table_slot.clear()
        with self.table_slot:
            with ui.element("div").classes("empty-box"):
                ui.html(icon_svg("warn", 34)).classes("empty-icon")
                ui.label("加载失败").classes("empty-title")
                ui.label(human_error(exc, "无法读取知识库")).classes("empty-text")
                with ui.element("div").classes("empty-actions"):
                    retry = ui.element("button").props("type=button").classes("btn-ghost")
                    retry.on("click", self.refresh)
                    with retry:
                        ui.html(icon_svg("refresh", 14))
                        ui.label("重试")

    def _render_disabled(self) -> None:
        self.stats_slot.clear()
        self.table_slot.clear()
        with self.table_slot:
            with ui.element("div").classes("empty-box"):
                ui.html(icon_svg("book", 34)).classes("empty-icon")
                ui.label("知识库未启用").classes("empty-title")
                ui.label(
                    "后端配置里 TPA_RAG_ENABLED=false。启用后重启后端，就可以上传资料并让助手引用。"
                ).classes("empty-text")

    def _set_actions_enabled(self, enabled: bool) -> None:
        for button in (self.upload_button, self.url_button):
            if button is None:
                continue
            if enabled:
                button.props(remove="disabled")
            else:
                button.props("disabled")

    # ------------------------------------------------------------------ 上传
    def _open_upload(self) -> None:
        if self.disabled:
            ui.notify("知识库未启用", type="warning", position="top")
            return
        if self.upload_dialog is not None:
            self.upload_dialog.open()

    def _open_url(self) -> None:
        if self.disabled:
            ui.notify("知识库未启用", type="warning", position="top")
            return
        if self.url_dialog is not None:
            self.url_dialog.open()

    def _dialogs(self) -> None:
        # ---- 上传文件 ----
        with ui.dialog() as self.upload_dialog, ui.card().classes("dialog-card").style(
            "width:min(520px,92vw)"
        ):
            ui.label("上传资料").classes("dialog-title")
            ui.label(
                "支持 pdf / docx / md / txt / csv，单文件 ≤ 20 MB。上传后会同步解析、分块并向量化，可能需要 5–30 秒。"
            ).classes("dialog-sub")
            with ui.element("div").classes("field").style("margin-top:4px"):
                ui.label("标题（可选）").classes("field-label")
                self.upload_title = (
                    ui.input(placeholder="留空则使用文件名")
                    .props("borderless")
                    .classes("field")
                    .style("width:100%")
                )
            upload = ui.upload(
                label="选择文件并开始上传",
                auto_upload=True,
                max_file_size=20 * 1024 * 1024,
                on_upload=self._handle_upload,
                on_rejected=lambda _=None: ui.notify(
                    "文件超过 20MB 或类型不支持", type="negative", position="top"
                ),
            ).classes("upload-box").props('accept=".pdf,.docx,.md,.txt,.csv"')
            self.uploader = upload
            upload.style("width:100%;margin-top:10px")
            ui.label("文件只保存在本机的 data/uploads 目录。").classes("dialog-note")
            with ui.element("div").classes("dialog-actions"):
                ui.button("关闭", color=None, on_click=self.upload_dialog.close).classes(
                    "btn-ghost"
                ).props("flat no-caps")

        # ---- 从网址添加 ----
        with ui.dialog() as self.url_dialog, ui.card().classes("dialog-card").style(
            "width:min(540px,92vw)"
        ):
            ui.label("从网址添加").classes("dialog-title")
            ui.label(
                "抓取网页正文入库。适合跟踪景区最新公告、交通新规这类会变的信息；只允许 http/https，单页 ≤ 5 MB。"
            ).classes("dialog-sub")
            with ui.element("div").classes("field").style("margin-top:4px"):
                ui.label("网址").classes("field-label")
                self.url_input = (
                    ui.input(placeholder="https://example.gov.cn/notice.html")
                    .props("borderless")
                    .classes("field")
                    .style("width:100%")
                )
            with ui.element("div").classes("field"):
                ui.label("标题（可选）").classes("field-label")
                self.url_title = (
                    ui.input(placeholder="留空则取网页标题")
                    .props("borderless")
                    .classes("field")
                    .style("width:100%")
                )
            with ui.element("div").classes("dialog-actions"):
                ui.button("取消", color=None, on_click=self.url_dialog.close).classes(
                    "btn-ghost"
                ).props("flat no-caps")
                submit = ui.button("抓取并入库", color=None).classes("btn-ink").props(
                    "unelevated no-caps"
                )
                submit.on("click", lambda: self._handle_url(submit))

        # ---- 处理中 ----
        with ui.dialog() as self.processing_dialog, ui.card().classes("dialog-card").style(
            "width:min(420px,90vw)"
        ):
            with ui.element("div").classes("processing"):
                ui.element("div").classes("ring")
                self.processing_title = ui.label("正在入库").classes("title")
                self.processing_text = ui.label(
                    "解析 → 清洗 → 分块 → 向量化 → 入库，通常需要 5–30 秒。"
                ).classes("text")
                ui.element("div").classes("progress-line").style("width:100%")

        # ---- 入库结果 ----
        with ui.dialog() as self.preview_dialog, ui.card().classes("dialog-card").style(
            "width:min(620px,92vw)"
        ):
            self.preview_title = ui.label("入库结果").classes("dialog-title")
            self.preview_meta = ui.label("").classes("dialog-sub")
            self.preview_body = ui.element("div").style("width:100%")
            with ui.element("div").classes("dialog-actions"):
                ui.button("知道了", color=None, on_click=self.preview_dialog.close).classes(
                    "btn-ink"
                ).props("unelevated no-caps")

    async def _handle_upload(self, event: Any) -> None:
        if self.loading:
            return
        name = str(getattr(event, "name", "") or "upload")
        title = (self.upload_title.value or "").strip() if self.upload_title else ""
        try:
            content = event.content.read()
        except Exception:
            content = b""
        self._show_processing("正在解析文件", f"{name} · 解析 → 清洗 → 分块 → 向量化 → 入库")
        try:
            data = await get_api().upload(
                "/api/v1/rag/documents",
                files={"file": (name, content, getattr(event, "type", "") or "application/octet-stream")},
                data={"title": title},
            )
            await self.refresh()
            if self.upload_dialog is not None:
                self.upload_dialog.close()
            if self.upload_title is not None:
                self.upload_title.value = ""
            try:
                if self.uploader is not None:
                    self.uploader.reset()
            except Exception:
                pass
            if str((data or {}).get("status")) == "ready":
                ui.notify(f"入库成功，共 {data.get('chunk_count') or 0} 块", type="positive", position="top")
                self._show_preview(data, success=True)
            else:
                ui.notify(f"入库失败：{(data or {}).get('error') or '未知原因'}", type="negative", position="top")
        except ApiError as exc:
            toast_error(exc)
        finally:
            self._hide_processing()

    async def _handle_url(self, button: Any) -> None:
        url = (self.url_input.value or "").strip() if self.url_input else ""
        title = (self.url_title.value or "").strip() if self.url_title else ""
        if not url:
            ui.notify("请填写网址", type="warning", position="top")
            return
        button.props("loading disable")
        self._show_processing("正在抓取网页", url)
        try:
            data = await get_api().post(
                "/api/v1/rag/documents/from-url", json={"url": url, "title": title or None}
            )
            await self.refresh()
            if self.url_dialog is not None:
                self.url_dialog.close()
            if self.url_input is not None:
                self.url_input.value = ""
            if self.url_title is not None:
                self.url_title.value = ""
            if str((data or {}).get("status")) == "ready":
                ui.notify(f"入库成功，共 {data.get('chunk_count') or 0} 块", type="positive", position="top")
                self._show_preview(data, success=True)
            else:
                ui.notify(f"入库失败：{(data or {}).get('error') or '未知原因'}", type="negative", position="top")
        except ApiError as exc:
            toast_error(exc)
        finally:
            button.props(remove="loading disable")
            self._hide_processing()

    def _show_processing(self, title: str, text: str) -> None:
        self.loading = True
        self.processing_title.text = title
        self.processing_text.text = text
        if self.processing_dialog is not None:
            self.processing_dialog.open()

    def _hide_processing(self) -> None:
        self.loading = False
        if self.processing_dialog is not None:
            self.processing_dialog.close()

    def _show_preview(self, data: dict[str, Any], success: bool) -> None:
        self.preview_title.text = "入库成功" if success else "入库失败"
        self.preview_meta.text = (
            f"{data.get('title') or '未命名'} · {data.get('chunk_count') or 0} 块 · "
            f"{'文件' if data.get('source_type') == 'file' else '网址'}"
        )
        self.preview_body.clear()
        with self.preview_body:
            chunks = data.get("chunk_preview") or []
            if chunks:
                ui.label("前 3 块预览（用来确认切分是否合理）").classes("panel-kicker").style(
                    "margin-top:12px"
                )
                with ui.element("div").classes("preview-chunks"):
                    for index, chunk in enumerate(chunks, start=1):
                        with ui.element("div").classes("preview-chunk"):
                            ui.label(f"CHUNK {index:02d}").classes("idx")
                            ui.label(str(chunk))
            else:
                ui.label(
                    str(data.get("error") or "没有可预览的文本块")
                ).classes("empty-text").style("text-align:left;margin-top:12px")
                if not success:
                    ui.label(
                        "常见原因：扫描版 PDF、页面需要登录、正文不足 50 字符。"
                    ).classes("dialog-note")
        self.preview_dialog.open()

    def _ask_delete(self, doc: dict[str, Any]) -> None:
        async def action() -> None:
            await get_api().delete(f"/api/v1/rag/documents/{doc.get('id')}")
            ui.notify("文档已删除", type="positive", position="top")
            await self.refresh()

        self.confirm.open(
            "删除这份资料？",
            f"《{doc.get('title') or '未命名资料'}》的文本块、向量与磁盘文件会一起删除，助手将不再引用它。",
            "删除",
            action,
            danger=True,
        )

    # ------------------------------------------------------------------ 检索调试
    def _search_panel(self) -> None:
        with ui.element("div").classes("search-panel"):
            ui.label("RAG / RETRIEVAL").classes("panel-kicker")
            ui.label("检索调试").classes("panel-title")
            ui.label(
                "用关键词直接查向量库。能区分「检索不到」和「检索到了但模型没用」——这是调 RAG 效果最快的地方。"
            ).classes("panel-desc")
            with ui.element("div").classes("search-bar"):
                with ui.element("div").classes("search-input"):
                    self.search_input = (
                        ui.input(placeholder="例如：西湖景区预约规则", on_change=self._on_search_change)
                        .props("borderless")
                        .classes("search-input")
                        .style("width:100%")
                    )
                search_btn = ui.element("button").props("type=button").classes("btn-ghost")
                search_btn.on("click", self._run_search)
                with search_btn:
                    ui.html(icon_svg("search", 14))
                    ui.label("检索")
            self.search_meta = ui.label("").classes("search-meta")
            self.search_results = ui.element("div").classes("search-results")

    def _on_search_change(self, _=None) -> None:
        self.search_seq += 1
        if self.search_timer is not None:
            try:
                self.search_timer.deactivate()
            except Exception:
                pass
        query = (self.search_input.value or "").strip() if self.search_input else ""
        if not query:
            self.search_meta.text = ""
            self.search_results.clear()
            return
        self.search_timer = ui.timer(0.5, self._search_from_input, once=True)

    async def _search_from_input(self) -> None:
        await self._run_search()

    async def _run_search(self, immediate: bool = False) -> None:
        query = (self.search_input.value or "").strip() if self.search_input else ""
        if not query:
            return
        if self.disabled:
            ui.notify("知识库未启用", type="warning", position="top")
            return
        self.search_seq += 1
        self.search_meta.text = "正在检索…"
        self.search_results.clear()
        try:
            data = await get_api().get("/api/v1/rag/search", params={"q": query})
        except ApiError as exc:
            self.search_meta.text = ""
            with self.search_results:
                ui.label(human_error(exc)).classes("auth-error")
            return
        hits = list((data or {}).get("hits") or [])
        elapsed = (data or {}).get("elapsed_ms")
        self.search_meta.text = f"q={query} · {elapsed}ms · 命中 {len(hits)} 条"
        self.search_results.clear()
        with self.search_results:
            if not hits:
                ui.label(
                    "没有匹配的片段。试试换关键词，或确认文档已入库。"
                ).classes("search-empty")
                return
            for hit in hits:
                with ui.element("div").classes("hit"):
                    with ui.element("div").classes("hit-head"):
                        ui.label(str(hit.get("title") or "未命名资料")).classes("hit-title")
                        ui.label(f"块 #{hit.get('ordinal', '—')}").classes("hit-meta")
                        try:
                            score = f"{float(hit.get('score')):.4f}"
                        except (TypeError, ValueError):
                            score = str(hit.get("score"))
                        ui.label(f"score {score}").classes("hit-score")
                    ui.label(str(hit.get("snippet") or "")).classes("hit-snippet")


@ui.page("/knowledge", title="知识库 · 出行计划助手", response_timeout=20)
async def knowledge_page() -> None:
    user = await require_root()
    if not user:
        return
    page = KnowledgePage(user)
    await page.build()
