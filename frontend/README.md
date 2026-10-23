# 行迹 · 出行计划助手前端

NiceGUI 2.x 服务端渲染前端。只通过 HTTP / WebSocket 消费后端契约，不 import `backend` 任何模块。

## 启动

```bash
# 后端先在 :8000 起好
python -m pip install -r requirements-frontend.txt
python -m frontend.main
# 打开 http://127.0.0.1:8080
```

默认使用 `data/app.db` 里的 root 账号（见后端 `.env` 的 `TPA_ROOT_USERNAME` / `TPA_ROOT_PASSWORD`）。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `TPA_BACKEND_BASE_URL` | `http://127.0.0.1:8000` | 后端地址，不要带尾部 `/` |
| `TPA_FRONTEND_PORT` | `8080` | 前端端口 |
| `TPA_FRONTEND_HOST` | `0.0.0.0` | 监听地址 |
| `TPA_FRONTEND_STORAGE_SECRET` | 内置 demo 串 | `ui.run(storage_secret=...)`，生产请换成随机串 |
| `TPA_MOCK` | `0` | `1` 时使用 `mock_store.py` 里的写死数据，无需后端 |
| `TPA_FRONTEND_RELOAD` | `TPA_ENV=dev` 时为 `1` | 开发热重载 |

## 没有后端时调 UI

```bash
$env:TPA_MOCK="1"; python -m frontend.main   # PowerShell
# TPA_MOCK=1 python -m frontend.main          # bash
```

Mock 提供 3 个会话、一份完整行程、知识库文档、用户列表，以及逐帧模拟的 WS（工具 → token → itinerary → done），
方便调行程卡片、工具面板、断线/取消状态。

## 目录

```
frontend/
├─ main.py                  # ui.run + "/" 路由
├─ config.py                # 环境变量与 WS 地址
├─ api_client.py            # httpx 封装 + MockApiClient
├─ ws_client.py             # websockets 封装 + MockChatSocket
├─ state.py                 # session / 页面守卫 / 错误文案
├─ theme.py                 # 视觉系统（CSS、线性图标、滚动 JS）
├─ ui_utils.py              # 金额/时长/日期格式化与小组件
├─ mock_store.py            # Mock 内存状态
├─ mock_data.py             # 写死的数据，含完整 itinerary
├─ components/
│  ├─ shell.py              # 侧栏、用户菜单、页面骨架
│  ├─ conversation_list.py  # 分组、重命名、删除
│  ├─ message_bubble.py     # Markdown / 复制 / 重试 / 引用 / 长 JSON 折叠
│  ├─ itinerary_card.py     # 行程卡片
│  ├─ tool_call_panel.py    # 工具调用面板
│  ├─ thinking_bar.py       # 顶部状态条
│  ├─ dialogs.py            # 确认、重命名、偏好、系统状态
│  └─ markdown_export.py    # 本地生成 Markdown
└─ pages/
   ├─ login.py
   ├─ chat.py
   ├─ knowledge.py
   └─ users.py
```

## 与文档的对应关系

- token 存在 `app.storage.user`，不进浏览器 localStorage；WS 客户端跑在 NiceGUI 进程里。
- 流式 token 只在 `_on_frame` 里累积，60ms 定时器统一刷 DOM；WS 回调不直接碰 UI。
- 断线按 `1s → 2s → 4s → 8s → 8s` 重连，成功后重拉整段消息。
- 行程卡片整个渲染包在 `try/except` 里；`itinerary` 为 `null` 时只显示文本。
- 导出行程不走接口：前端自己拼 Markdown 再触发浏览器下载。
- 模型偶尔把 `itinerary` 直接写在回复的 ```` ```json ```` 里（后端解析失败时），前端会把超过 280 字的长 JSON 折叠成
  「结构化行程数据」，默认收起，不遮挡正文。

> `requirements-frontend.txt` 把 NiceGUI 限制在 `<3`：NiceGUI 3.x 要求 `starlette>=1.3`，会与后端钉死的
> `fastapi==0.128.8` / `starlette==0.52.1` 冲突。
