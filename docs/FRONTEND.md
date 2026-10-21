# 出行计划智能助手 —— 前端开发文档

| 项 | 内容 |
|---|---|
| 适用范围 | 前端工程师 |
| 版本 | Demo v1.0 |
| 技术栈 | NiceGUI 2.x（纯 Python，服务端渲染） + httpx + websockets |
| 代码量估算 | 约 700–900 行 |
| 契约依据 | [后端文档](BACKEND.md)（字段、错误码、帧格式一律以后端文档为准） |

> **本文档只讲"怎么调、怎么显示"。** 任何字段名、错误码、WS 帧结构有疑问，去看 [BACKEND.md](BACKEND.md)。

---

## 目录

- [1. 职责与边界](#1-职责与边界)
- [2. 技术选型与项目结构](#2-技术选型与项目结构)
- [3. 页面与路由](#3-页面与路由)
- [4. 后端接口消费清单](#4-后端接口消费清单)
- [5. api_client 封装](#5-api_client-封装)
- [6. ws_client 封装](#6-ws_client-封装)
- [7. 组件设计](#7-组件设计)
- [8. 行程卡片渲染规则](#8-行程卡片渲染规则)
- [9. 对话页交互状态机](#9-对话页交互状态机)
- [10. 管理页面](#10-管理页面)
- [11. 错误与空态](#11-错误与空态)
- [12. 启动与调试](#12-启动与调试)

---

## 1. 职责与边界

### 1.1 前端负责

| # | 职责 |
|---|---|
| F1 | 页面渲染：登录、对话、知识库管理、用户管理 |
| F2 | 登录态维护：token 存储、失效跳转 |
| F3 | 与后端通信：REST（httpx）+ WebSocket（websockets） |
| F4 | 流式渲染：逐字追加文本、工具调用过程可视化 |
| F5 | 行程卡片：把行程 JSON 渲染成时间轴 |
| F6 | 文件下载：导出行程 Markdown |
| F7 | 交互状态：生成中锁输入框、取消按钮、失败重试 |

### 1.2 前端**不**负责

| 不负责 | 说明 |
|---|---|
| 不直连数据库 | —— |
| 不调 LLM、不持高德 Key | 全部在后端 |
| 不 import 后端任何模块 | 只走 HTTP/WS。这条是硬约束，违反后前端就无法替换 |
| 不自行拼业务规则 | 比如"能不能取消"由后端状态决定，前端只如实反映 |

### 1.3 一个关键架构选择：WS 连接建在**服务端**

NiceGUI 是服务端渲染框架，页面逻辑跑在 Python 服务里。因此：

```
浏览器 ──(NiceGUI 自己的 socket.io)──► 前端服务:8080 ──(WebSocket)──► 后端:8000
```

**WS 客户端跑在前端服务进程里，不在浏览器里。** 带来三个好处：

| 好处 | 说明 |
|---|---|
| token 不进浏览器 | 存在 `app.storage.user`（服务端存储），XSS 也偷不到 |
| 不用写 JS | 帧处理和状态机全是 Python，调试方便 |
| 服务端渲染天然支持 | 刷新页面时服务端还握着会话状态 |

代价：慢网络的逐字效果依赖 NiceGUI 自己的通道（通常没问题）。Demo 阶段这个取舍很划算。

---

## 2. 技术选型与项目结构

| 用途 | 选型 |
|---|---|
| UI 框架 | NiceGUI `>=2.0`（内置 Vue/Quasar，无需写前端构建） |
| REST 客户端 | httpx（async） |
| WS 客户端 | websockets `>=12` |
| Markdown 渲染 | NiceGUI `ui.markdown`（**默认不渲染原始 HTML**，安全） |
| 图表 | 不需要（预算用 `ui.linear_progress` 或纯 div 条） |

```
frontend/
├─ main.py              # ui.run() + 页面注册
├─ config.py            # TPA_BACKEND_BASE_URL、端口
├─ api_client.py        # REST 封装
├─ ws_client.py         # WebSocket 封装
├─ state.py             # 页面级状态对象（token、当前会话、累积文本）
├─ components/
│  ├─ message_bubble.py
│  ├─ itinerary_card.py
│  ├─ tool_call_panel.py
│  └─ conversation_list.py
└─ pages/
   ├─ login.py
   ├─ chat.py
   ├─ knowledge.py      # root
   └─ users.py          # root
```

`requirements-frontend.txt`：`nicegui>=2.0`、`httpx>=0.27`、`websockets>=12`

**前端自己的 2 个环境变量**

```ini
TPA_BACKEND_BASE_URL=http://127.0.0.1:8000
TPA_FRONTEND_PORT=8080
```

外加 `ui.run()` 必须传 `storage_secret`（NiceGUI 用它加密服务端存储）：

```python
ui.run(host="0.0.0.0", port=8080, storage_secret="换成你自己的随机串",
       title="出行计划助手", reload=(env == "dev"))
```

---

## 3. 页面与路由

### 3.1 路由表（6 个路由 / 4 个页面模块）

| 路由 | 文件 | 权限 | 内容 |
|---|---|---|---|
| `/` | `main.py` 内联 | 🔓 | 已登录跳 `/chat`，未登录跳 `/login` |
| `/login` | `pages/login.py` | 🔓 | 登录 / 注册（Tab 切换） |
| `/chat` | `pages/chat.py` | 👤 | 新会话状态（无消息） |
| `/chat/{conversation_id}` | `pages/chat.py` | 👤 | 指定会话 |
| `/knowledge` | `pages/knowledge.py` | 👑 | 文档管理 |
| `/users` | `pages/users.py` | 👑 | 用户管理 |

> `/chat` 和 `/chat/{id}` 是**同一个页面函数**，用可选路径参数区分：`@ui.page("/chat")` + `@ui.page("/chat/{conversation_id}")` 装饰两次同一个函数。

### 3.2 登录态与守卫

```python
# state.py
def save_session(token: str, user: dict) -> None:
    app.storage.user.update({"token": token, "user": user})

def clear_session() -> None:
    app.storage.user.pop("token", None)
    app.storage.user.pop("user", None)

def current_user() -> dict | None:
    return app.storage.user.get("user")

def require_user() -> dict | None:
    u = current_user()
    if not u:
        ui.navigate.to("/login")
    return u

def require_root() -> dict | None:
    u = require_user()
    if u and u.get("role") != "root":
        ui.navigate.to("/chat")          # 越权直接踢回
        return None
    return u
```

每个 `@ui.page` 函数第一行调用守卫，不通过就 `return`（**必须 return**，否则页面会继续构建）：

```python
@ui.page("/knowledge")
def knowledge_page():
    if not require_root():
        return
    ...
```

> 前端守卫只是"体验优化"。真正的权限校验在后端（访问 `/api/v1/rag/*` 会返回 403）。前端不能作为安全边界。

### 3.3 登录页

```
┌────────────────────────────────┐
│        出行计划助手             │
│  ┌──────────┬──────────┐       │
│  │   登录    │   注册    │       │  ← ui.tabs
│  └──────────┴──────────┘       │
│  用户名 [_______________]      │
│  密码   [_______________]      │
│         [   进入   ]           │
└────────────────────────────────┘
```

| 交互 | 行为 |
|---|---|
| 提交成功 | `save_session(token, user)` → `ui.navigate.to("/chat")` |
| `AUTH_BAD_CREDENTIALS` | 表单下方红字"用户名或密码错误" |
| `AUTH_WEAK_PASSWORD` | "密码至少 8 位" |
| `AUTH_USERNAME_TAKEN` | "用户名已被占用" |
| `AUTH_REGISTER_CLOSED` | 隐藏注册 Tab，提示"请联系管理员开号" |
| 回车 | 提交（`ui.input(..., on_keydown)` 监听 Enter） |

**注册说明文案**：注册后自动登录（后端直接返回 token），不需要二次输入。

---

## 4. 后端接口消费清单

| 前端动作 | 调用 | 备注 |
|---|---|---|
| 登录 / 注册 | `POST /auth/login`、`POST /auth/register` | 返回 token + user |
| 任意页面进入时校验登录态 | `GET /auth/me` | 顺便拿最新 `role`（可能被管理员改过） |
| 保存画像 | `PUT /auth/profile` | 整体替换 |
| 会话列表 | `GET /conversations` | 按 `updated_at` 倒序 |
| 新建会话 | `POST /conversations` | 可以先建会话再发消息，也可以懒创建 |
| 进入会话 | `GET /conversations/{id}/messages` | **一次拿回 conversation + 全部消息** |
| 改标题 | `PATCH /conversations/{id}` | —— |
| 删会话 | `DELETE /conversations/{id}` | 二次确认 |
| 发消息（主） | `WS /ws/chat` | 帧格式见第 6 章 |
| 发消息（备用） | `POST /conversations/{id}/messages` | 只在 WS 连不上时用 |
| 取消生成 | WS `cancel` 帧 | —— |
| 断线补拉 | `GET /conversations/{id}/messages` | 重连后调一次即可 |
| 导出行程 | 本地生成 Markdown 字符串 + 浏览器下载 | **不走接口**，见 8.5 |
| 知识库：上传 | `POST /rag/documents`（multipart） | 同步，可能等 5–30 秒 |
| 知识库：URL 入库 | `POST /rag/documents/from-url` | —— |
| 知识库：列表 | `GET /rag/documents` | —— |
| 知识库：删除 | `DELETE /rag/documents/{id}` | 二次确认 |
| 知识库：检索调试 | `GET /rag/search?q=...` | 排查效果用 |
| 用户列表 | `GET /admin/users` | —— |
| 改用户角色/状态 | `PATCH /admin/users/{id}` | —— |
| 工具状态 | `GET /tools` | 可选，做一个"系统状态"折叠面板 |
| 手动调工具 | `POST /tools/{name}/invoke` | 可选，排障用 |

> **导出行程为什么不走接口**：后端文档里没有导出接口。前端已经拿到完整 `itinerary` JSON，直接在本地拼 Markdown 再触发下载更简单，也少一次往返。后端的 `export_service.py` 可留作脚本用，不必暴露接口。

---

## 5. api_client 封装

### 5.1 设计目标

| 目标 | 做法 |
|---|---|
| 自动带 token | 从 `app.storage.user` 读，不每个调用点手传 |
| 统一错误 | 后端信封 `{ok,data,error}` 转成异常 `ApiError(code, message)` |
| 401 统一处理 | 清 session + 跳登录页，调用方不用管 |
| 单例 client | 复用连接，别每次请求新建 `AsyncClient` |

### 5.2 接口

```python
class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int): ...


class ApiClient:
    def __init__(self, base_url: str):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=90)

    async def post(self, path: str, json: dict | None = None) -> dict: ...
    async def get(self, path: str, params: dict | None = None) -> dict: ...
    async def patch(self, path: str, json: dict) -> dict: ...
    async def delete(self, path: str) -> dict: ...
    async def upload(self, path: str, files: dict, data: dict) -> dict: ...
```

**核心方法体（约 20 行）**

```python
async def _request(self, method, path, **kw) -> dict:
    token = app.storage.user.get("token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = await self._client.request(method, path, headers=headers, **kw)

    if resp.status_code == 401:
        clear_session()
        ui.navigate.to("/login")
        raise ApiError("AUTH_TOKEN_INVALID", "登录已过期", 401)

    body = resp.json()
    if not body.get("ok"):
        err = body.get("error") or {}
        raise ApiError(err.get("code", "INTERNAL_ERROR"),
                       err.get("message", "请求失败"), resp.status_code)
    return body.get("data")
```

**超时设 90 秒**：非流式发消息接口最长可能 60 秒 + 余量。

### 5.3 调用点写法

```python
try:
    data = await api.post(f"/api/v1/conversations/{cid}/messages",
                          json={"content": text})
except ApiError as e:
    ui.notify(e.message, type="negative")
```

不要写 `if resp.status_code == 200` 这种判断——错误已经在封装层转成异常了。

---

## 6. ws_client 封装

### 6.1 目标

`ws_client.py` **只管连接、收发、重连**，不碰 UI。UI 通过回调消费帧。

```python
class ChatSocket:
    def __init__(self, ws_url: str, on_frame: Callable[[dict], None]): ...

    async def connect(self, token: str) -> None
    async def send_message(self, conversation_id: str, content: str) -> None
    async def send_cancel(self, conversation_id: str) -> None
    async def close(self) -> None

    # 内部
    async def _reader_loop(self) -> None
    async def _reconnect_loop(self) -> None
```

### 6.2 连接与认证

```python
async def connect(self, token: str) -> None:
    self._ws = await websockets.connect(self._url, max_size=1 << 20)
    await self._ws.send(json.dumps({"type": "auth", "data": {"token": token}}))

    raw = await asyncio.wait_for(self._ws.recv(), timeout=10)
    frame = json.loads(raw)
    if frame["type"] != "auth_ok":
        raise ApiError("AUTH_TOKEN_INVALID", "登录已过期", 401)

    self._task = asyncio.create_task(self._reader_loop())
```

**认证 10 秒超时**：后端 10 秒内没收到 `auth` 就关连接（`4001`）。所以 `connect()` 里收到 `auth_ok` 才算连成功。

### 6.3 帧分发

```python
async def _reader_loop(self) -> None:
    try:
        async for raw in self._ws:
            frame = json.loads(raw)
            self._on_frame(frame)          # 交给页面，不做任何业务判断
    except websockets.ConnectionClosed:
        self._on_frame({"type": "_disconnected", "data": None})
        await self._reconnect_loop()
```

### 6.4 重连策略

| 项 | 规定 |
|---|---|
| 触发 | 非主动关闭（`close()` 不算） |
| 退避 | 1s → 2s → 4s → 8s → 8s，最多 5 次 |
| 重连后动作 | ① 用当前 token 重新 `auth` ② 回调 `_reconnected` 事件让页面补拉消息 |
| 放弃 | 5 次都失败 → 回调 `_gaveup`，页面显示"连接已断开，请刷新页面" |
| token 失效 | 重连时收到 `4001` → 清 session + 跳登录页，不重试 |

```python
async def _reconnect_loop(self) -> None:
    for delay in (1, 2, 4, 8, 8):
        await asyncio.sleep(delay)
        try:
            await self.connect(app.storage.user["token"])
            self._on_frame({"type": "_reconnected", "data": None})
            return
        except ApiError:
            clear_session(); ui.navigate.to("/login"); return
        except Exception:
            continue
    self._on_frame({"type": "_gaveup", "data": None})
```

### 6.5 页面侧帧处理

页面维护一个"当前轮次"的累积状态，收到帧就更新：

```python
def _on_frame(self, frame: dict) -> None:
    t = frame["type"]

    if t == "_reconnected":
        asyncio.create_task(self._backfill())      # 补拉消息
        return
    if t == "auth_ok":
        return
    if t == "tool":
        self.tool_events.append(frame["data"])
        return
    if t == "token":
        self.buf += frame["data"]["delta"]         # 只累积，不直接刷 UI
        return
    if t == "itinerary":
        self.pending_itinerary = frame["data"]
        return
    if t == "error":
        ui.notify(frame["data"]["message"], type="negative")
        self.finish_round(status="failed")
        return
    if t == "done":
        d = frame["data"]
        self.final_content = d["message"]["content"]   # 用它覆盖累积文本
        self.pending_itinerary = None                  # 已落库，以补拉为准
        self.finish_round(status=d["status"], title=d.get("title"))
        return
```

### 6.6 渲染节流（必须做）

`token` 帧可能 30 次/秒。直接每帧刷新 DOM 会卡。

```python
# 页面初始化时注册一次
ui.timer(0.06, self._flush_buffer)     # 每 60ms 刷一次

def _flush_buffer(self) -> None:
    if not self.buf or not self.streaming_bubble:
        return
    self.streaming_bubble.set_content(self.buf)
    self.scroll_to_bottom()
```

**为什么不在 `_on_frame` 里直接改 UI**：NiceGUI 的 UI 更新必须在客户端上下文的主循环里做。`_on_frame` 是从 WS 协程调过来的，只往普通 Python 变量里写数据最安全。

### 6.7 断线补拉

```python
async def _backfill(self) -> None:
    data = await api.get(f"/api/v1/conversations/{self.conversation_id}/messages")
    self.render_messages(data["items"])      # 整段重渲染
    self.title = data["conversation"]["title"]
```

**补拉就是整段重渲染**，不做增量合并。消息量在 200 条内，整段重渲染最简单也最不容易出 bug（不需要按 `message_id` 去重对齐）。

---

## 7. 组件设计

### 7.1 `MessageBubble`

| 输入 | 行为 |
|---|---|
| `role=user` | 右对齐、无头像；内容按纯文本渲染（不渲染 Markdown，防止用户输入被当格式解析） |
| `role=assistant` | 左对齐；内容 `ui.markdown(...)` 渲染 |
| `status=streaming` | 右下角显示闪烁光标，输入框禁用 |
| `status=failed` | 气泡内显示红色提示条 + "重试"按钮 |
| `status=cancelled` | 显示灰色"已停止生成"标记，内容保留 |

**操作按钮**（hover 显示）：复制、重试（仅失败时）。

**重试语义**：把原用户消息内容重新发一次（走 WS），不复用旧消息。

### 7.2 `ToolCallPanel`

默认**收起**，只显示一行摘要：

```
🔧 已调用 4 个工具 · 1.4s
```

展开后逐条：

```
✔ weather_forecast   weather   312ms   3/22 多云 18–24℃；3/23 阵雨 16–21℃
✔ place_search       place     402ms   命中 128 条，取前 10
✔ geo_geocode        place     180ms   已定位北山街
✔ route_plan         place     620ms   4.8km / 19 分钟
```

| 项 | 规则 |
|---|---|
| 图标 | `✔` 成功 / `✖` 失败（`ok=false`） |
| 失败项 | 点击展开显示 `error.code` 与 `message`（开发者信息，普通用户默认不展开） |
| 数据来源 | 收到 `tool` 帧时累积；`done` 后用补拉的消息里的 `tool_calls` 覆盖（以服务端为准） |
| 折叠状态 | 存在 `app.storage.tab`，同标签页内保持一致 |

**`start` 与 `end` 配对**：用 `name` 配对（Demo 不并发调同一工具，够用）。收到 `start` 显示 `⏳`，收到 `end` 替换成 `✔/✖`。

### 7.3 `ConversationList`

```
┌───────────────────────┐
│ [+ 新建对话]           │
├───────────────────────┤
│ 杭州周末两天      ⋮    │◄ 当前选中高亮
│ 6 条 · 已生成行程      │
├───────────────────────┤
│ 北京出差三天      ⋮    │
│ 2 条                  │
└───────────────────────┘
```

| 交互 | 行为 |
|---|---|
| 点击项 | 跳 `/chat/{id}` |
| `⋮` → 重命名 | 弹 `ui.dialog` 输入框 → `PATCH` → 本地更新标题 |
| `⋮` → 删除 | 二次确认 → `DELETE` → 若删的是当前会话则跳 `/chat` |
| 新建 | `POST /conversations` → 跳 `/chat/{new_id}` |

**"已生成行程"徽标**：来自列表接口的 `has_itinerary` 字段。

### 7.4 `ThinkingBar`

页面顶部一条细状态条，根据帧更新：

| 触发 | 显示 |
|---|---|
| 发出 `message` 后 | `正在思考…` |
| 收到 `tool{phase:start}` | `正在调用 {name}…`（用工具名映射成人话，见下表） |
| 收到 `tool{phase:end}` | 保留 0.5 秒后回到 `正在组织答案…` |
| 收到首个 `token` | 状态条淡出 |
| 收到 `done` | 消失 |

**工具名 → 人话映射**

| 工具 | 文案 |
|---|---|
| `weather_now` | 正在查询实时天气… |
| `weather_forecast` | 正在查询天气预报… |
| `place_search` | 正在搜索地点… |
| `geo_geocode` | 正在定位地址… |
| `route_plan` | 正在计算路线… |
| `search_knowledge_base` | 正在检索知识库… |

> 这个映射表是前端唯一"硬编码业务文案"的地方，加工具时要同步加一行。

---

## 8. 行程卡片渲染规则

### 8.1 布局

```
┌────────────────────────────────────────────────────────┐
│ 杭州周末 2 日游                          [导出行程]    │
│ 2025-03-22 ~ 03-23 · 2 天 · 2 人                       │
│ 预算 ¥1500  ■交通400 ■住宿500 ■餐饮300 ■门票200 ■其他100│
├────────────────────────────────────────────────────────┤
│ ▸ 第 1 天 · 03-22 星期六 · 西湖环线    [多云 18–24℃]   │
│   09:00–11:30  断桥残雪 → 白堤 → 孤山                   │
│                📍 西湖区北山街 · 免费 · 150 分钟         │
│                ↳ 步行 5 分钟 380m                      │
│                💡 建议 9 点前到，10 点后人流明显增多     │
│   12:00–13:00  午餐：知味观（仁和路店）                 │
│                📍 上城区仁和路83号 · ¥160 · 60 分钟     │
├────────────────────────────────────────────────────────┤
│ ⚠ 风险提示                                              │
│ · 周日阵雨，户外项目受限 → 已安排室内备选：浙江省博物馆   │
├────────────────────────────────────────────────────────┤
│ 🧳 建议携带：雨伞、舒适步行鞋                            │
└────────────────────────────────────────────────────────┘
```

### 8.2 字段渲染规则（逐条照做）

| 字段 | 规则 |
|---|---|
| `title` | 卡片标题 |
| `start_date` / `end_date` / `day_count` / `travelers.adults` | 副标题一行：`2025-03-22 ~ 03-23 · 2 天 · 2 人`（`children > 0` 时补 `+1 儿童`） |
| `budget.total_cent` | `¥1500`（**分转元，去掉小数**） |
| `budget.breakdown` | 横向堆叠条，每段颜色固定，hover 显示名称+金额 |
| `days[]` | 每天一个可折叠区块，默认全展开 |
| `days[].weather` | 标题右侧徽标 `多云 18–24℃`；`weather` 为 `null` 时不显示 |
| `items[].start_time` / `end_time` | `09:00–11:30`；任一为 `null` 时显示"时间待定" |
| `items[].title` | 加粗 |
| `items[].location.address` | 第二行，`📍` 前缀；`null` 时只显示 `name` |
| `items[].cost_cent` | `0` → 显示"免费"（**不是 ¥0**）；否则 `¥160` |
| `items[].duration_min` | `150 分钟`；`>= 60` 时显示 `2 小时 30 分` 更易读 |
| `items[].transport` | 第三行 `↳ 步行 5 分钟 380m`；为 `null` 时整行不渲染 |
| `items[].notes` | 第四行，`💡` 前缀；空串时不渲染 |
| `items[].source == "model"` | **整行加灰色左边框 + 右上角"模型推断"小标签**（透明度 60%） |
| `risks[]` | 底部折叠区，`⚠ 风险提示`，每行 `description → mitigation` |
| `packing_list[]` | 底部一行 `🧳 建议携带：雨伞、舒适步行鞋`；空数组不渲染 |

### 8.3 `source` 标记为什么重要

`source` 有三个值：

| 值 | 含义 | 渲染 |
|---|---|---|
| `tool` | 来自工具查询（有数据支撑） | 正常 |
| `rag` | 来自知识库（有文档支撑） | 正常 |
| `model` | 模型推断（**没有数据支撑**） | 灰底 + "模型推断"标签 |

这是**抑制幻觉的产品级手段**。不是在提示词里写"别编造"，而是让用户一眼看出哪句话是编的——编造立刻可见，模型自己也会更谨慎（因为提示词里告诉它这个字段会被展示）。

**实现建议**：给 `model` 行的 `background` 加 4% 灰、左边框 3px 灰、右上角小标签。

### 8.4 空值与异常处理

| 情况 | 处理 |
|---|---|
| `itinerary` 为 `null` | **不渲染卡片**，只显示文本回复，导出按钮不出现 |
| `days` 为空数组 | 不渲染卡片 |
| `items` 为空数组 | 该天显示"自由活动"占位 |
| `budget` 缺失 | 不显示预算条（后端 Schema 要求必有，但防御性处理） |
| 字段类型不符 | 用 `.get()` 取值 + 默认值，**绝不让渲染抛异常炸掉整个消息** |

> 最后一条很重要：卡片是"增强显示"，它出错不能影响文本回复的展示。整个卡片渲染包在 try/except 里，失败就静默不显示卡片。

### 8.5 导出 Markdown（本地生成，不走接口）

```python
def build_markdown(it: dict) -> str:
    lines = [f"# {it['title']}", ""]
    lines.append(f"- 目的地：{it['destination']['name']}（adcode {it['destination']['adcode']}）")
    lines.append(f"- 日期：{it['start_date']} ~ {it['end_date']}（{it['day_count']} 天）")
    lines.append(f"- 出行人数：{it['travelers']['adults']} 成人")
    lines.append(f"- 预算：¥{it['budget']['total_cent'] // 100}")
    lines.append("")
    lines.append("## 行程")
    for d in it["days"]:
        lines.append("")
        lines.append(f"### 第 {d['date'][-2:]} 天 · {d['date']} · {d['weekday']} · {d['theme']}")
        w = d.get("weather")
        if w:
            lines.append(f"> 天气：{w['condition']} {w['temp_low_c']}–{w['temp_high_c']}℃")
        for item in d["items"]:
            t = f"{item['start_time'] or '—'}–{item['end_time'] or '—'}"
            cost = "免费" if item["cost_cent"] == 0 else f"¥{item['cost_cent'] // 100}"
            lines.append(f"- {t} **{item['title']}**")
            loc = item.get("location") or {}
            if loc.get("address"):
                lines.append(f"  - 位置：{loc['address']}")
            lines.append(f"  - 费用：{cost}｜时长：{item['duration_min']} 分钟")
            if item.get("notes"):
                lines.append(f"  - 备注：{item['notes']}")
    if it.get("risks"):
        lines.append("")
        lines.append("## 风险提示")
        for r in it["risks"]:
            lines.append(f"- {r['description']} → {r['mitigation']}")
    if it.get("packing_list"):
        lines.append("")
        lines.append(f"**建议携带**：{'、'.join(it['packing_list'])}")
    return "\n".join(lines)
```

**触发下载**（NiceGUI）：

```python
ui.download.content(build_markdown(it).encode("utf-8"),
                    filename=f"{safe_name(it['title'])}.md")
```

`filename` 要过滤 `/`、`\`、`:` 等非法字符，长度 ≤64。

---

## 9. 对话页交互状态机

### 9.1 状态定义

| 状态 | 界面表现 | 输入框 |
|---|---|---|
| `IDLE` | 无状态条，可发消息 | 启用 |
| `SENDING` | 状态条"正在发送…" | 禁用 |
| `STREAMING` | 状态条随工具更新，气泡逐字追加 | 禁用（发送按钮变"停止"） |
| `CANCELLING` | 状态条"正在停止…" | 禁用 |
| `FAILED` | 失败气泡 + 重试按钮 | 启用 |
| `DISCONNECTED` | 顶部黄条"连接已断开，正在重连…" | 禁用 |

### 9.2 转换

```
IDLE ──send──► SENDING ──ack?*──► STREAMING ──done{completed}──► IDLE
                  │                    │
                  │ error              ├──done{cancelled}──► IDLE
                  ▼                    │
               FAILED ──retry──► SENDING
                                       └──done{failed}──► FAILED

任意 ──连接断开──► DISCONNECTED ──重连成功──► IDLE（并补拉）
```

\* Demo 的 WS 协议没有 `ack` 帧（后端文档第 11 章只有 5 种下行帧），所以 `SENDING` 直接进入 `STREAMING`——发出 `message` 立刻切，收到首个 `tool` 或 `token` 帧时状态条才开始变。

### 9.3 取消

| 项 | 规定 |
|---|---|
| 触发 | 发送按钮变成"停止"图标 |
| 行为 | WS 发 `cancel` 帧 → 进 `CANCELLING` |
| 结果 | 收到 `done{status:"cancelled"}` → 保留已生成内容 + 灰色"已停止生成"标记 |
| 超时 | 3 秒没收到 `done` → 提示"停止请求已发出，正在收尾" |

### 9.4 防重复提交

| 手段 | 说明 |
|---|---|
| 输入框禁用 | `STREAMING`/`SENDING`/`CANCELLING` 期间禁用 |
| 空内容拦截 | 去空白后为空不发送 |
| 长度限制 | >8000 字符时提示，不发送 |

> 后端也会返回 `CONV_BUSY`，前端收到就在 toast 里提示，不改变状态（因为后端状态才是真相）。

### 9.5 滚动策略

| 时机 | 行为 |
|---|---|
| 新消息插入 | 滚到底 |
| 流式追加 | **仅当用户已在底部附近**（距底部 <100px）才自动滚到底，否则不打扰用户向上翻看 |
| 用户手动上滚 | 出现"回到底部"悬浮按钮 |

---

## 10. 管理页面

### 10.1 知识库页（`/knowledge`）

```
┌──────────────────────────────────────────────────────┐
│ 知识库             [+ 上传文件]  [+ 从网址添加]       │
├──────────────────────────────────────────────────────┤
│ 标题                   类型   状态    块数   操作      │
│ 杭州西湖景区预约须知    文件   ready   24    [删]      │
│ 交通管制通知            文件   failed   0    [删]      │
│ 2 月限行新规            网址   ready   12    [删]      │
├──────────────────────────────────────────────────────┤
│ 检索调试：[西湖预约规则____]  [检索]                   │
│  q=西湖景区预约规则 · 46ms · 命中 1 条                │
│  ┌ 杭州西湖景区预约须知 · 块#3 · 0.812                │
│  │ 自 2025 年 3 月 1 日起，西湖景区实行分时段预约…    │
└──────────────────────────────────────────────────────┘
```

**上传交互（关键）**

```python
async def on_upload(e):
    spinner.open()
    try:
        data = await api.upload("/api/v1/rag/documents",
                                files={"file": (e.name, e.content)},
                                data={"title": title_input.value or ""})
        if data["status"] == "ready":
            ui.notify(f"入库成功，共 {data['chunk_count']} 块", type="positive")
        else:
            ui.notify(f"入库失败：{data.get('error')}", type="negative")
        await refresh_table()
    finally:
        spinner.close()
```

| 要点 | 说明 |
|---|---|
| 必须显示 loading | 同步接口可能等 30 秒，不显示 loading 用户会以为卡死 |
| `status=failed` 不算异常 | 后端返回 201 + `status`，要按 `status` 分支判断，不要 try/except |
| `chunk_preview` | 上传成功后弹窗显示前 3 块，让 root 一眼看出切得对不对 |
| 失败行标红 | 表格里 `status=failed` 的行加红色背景，hover 显示 `error` |

**检索调试框**：每次输入变化后 500ms 防抖再查（`ui.timer` 或 `ui.input(on_change)` + `asyncio.sleep`）。显示 `score` 是排障的关键信息。

### 10.2 用户页（`/users`）

```
┌────────────────────────────────────────────────────────┐
│ 用户                                                    │
├────────────────────────────────────────────────────────┤
│ 用户名   角色    状态      会话数   操作                 │
│ root     root    active    3        ——（自己，禁用）     │
│ alice    user    active    12       [设为 root] [禁用]   │
│ bob      user    disabled  0        [设为 user] [启用]   │
└────────────────────────────────────────────────────────┘
```

| 规则 | 实现 |
|---|---|
| 自己的行 | 操作按钮全部 disabled，tooltip"不能修改自己的账号" |
| 最后一个 active root | 降级/禁用按钮 disabled，tooltip"系统必须保留一个可用的 root" |
| 禁用/降级 | `ui.dialog` 二次确认 |
| 显示会话数 | 只显示**数量**，不提供任何查看对话内容的入口（这是隐私边界，前端也不该做这个功能） |

---

## 11. 错误与空态

### 11.1 错误码 → 提示文案

| error_code | 提示 | 处理 |
|---|---|---|
| `AUTH_BAD_CREDENTIALS` | 用户名或密码错误 | 表单内红字 |
| `AUTH_TOKEN_INVALID` | 登录已过期 | 清 session → 跳登录页 |
| `AUTH_DISABLED` | 账号已被禁用，请联系管理员 | 跳登录页 |
| `AUTH_REGISTER_CLOSED` | 系统未开放注册 | 隐藏注册 Tab |
| `FORBIDDEN` | 需要管理员权限 | toast + 跳 `/chat` |
| `NOT_FOUND` | 会话不存在或已被删除 | toast + 跳 `/chat` |
| `CONV_BUSY` | 正在生成回复，请稍候 | toast，不改变状态 |
| `MSG_EMPTY` | 消息不能为空 | 本地拦截，不该到这一步 |
| `LLM_TIMEOUT` | 生成超时，已保留部分内容 | 失败气泡 + 重试 |
| `LLM_FAILED` | 模型暂时不可用 | 失败气泡 + 重试 |
| `TOOL_UNAVAILABLE` | 该能力当前不可用 | toast（对话仍会继续） |
| `RAG_DISABLED` | 知识库未启用 | 知识库页显示空态说明 |
| `RAG_FILE_TYPE` | 不支持该文件类型（支持 pdf/docx/md/txt/csv） | toast |
| `RAG_FILE_TOO_LARGE` | 文件超过 20MB | toast |
| `RAG_EMPTY_TEXT` | 未能提取到文本，可能是扫描版 | toast |
| `RAG_URL_BLOCKED` | 该网址不允许抓取 | toast |
| `INTERNAL_ERROR` | 服务出错了，请稍后再试 | toast |
| 网络异常 | 无法连接服务器 | 顶部黄条 |

### 11.2 空态

| 位置 | 空态设计 |
|---|---|
| 会话列表为空 | 居中插画 + "开始第一次出行规划" + 3 条示例问题（点击填入输入框） |
| 新会话无消息 | 大号引导："告诉我你要去哪、什么时候、几个人、预算多少" + 3 个示例 chip |
| 知识库无文档 | "还没有文档。上传景区公告、交通新规等资料，助手回答时会引用它们" |
| 检索无命中 | "没有匹配的片段。试试换关键词，或确认文档已入库" |
| 用户列表为空 | 不可能出现（至少有 root），但兜底显示"暂无用户" |

**3 个示例问题**（写死在代码里，改动成本低、演示效果好）

```
这周末去杭州玩两天，两个人，预算 1500
下周去成都出差三天，有什么值得去的地方
带爸妈去苏州一日游，不想走太多路
```

### 11.3 降级提示

后端 `/tools` 返回 `degraded=true` 时，在对话页顶部显示一条黄色横幅：

```
⚠ 地点服务暂时不可用，本次规划可能缺少景点信息
```

这条横幅**不阻塞输入**。对话能力本身没坏。

---

## 12. 启动与调试

### 12.1 启动

```bash
pip install -r requirements-frontend.txt
# 先确保后端已在 :8000 运行
python -m frontend.main
# 打开 http://127.0.0.1:8080
```

### 12.2 没有后端时怎么开发 UI

前端有两种联调方式：

| 方式 | 做法 |
|---|---|
| 起真后端 | 推荐。整个链路最真实 |
| Mock | 在 `api_client.py` 里加一个 `MOCK` 开关，返回写死的 JSON（含一份完整 `itinerary`），专门用来调卡片样式 |

**建议**：先用手写的 `itinerary.json` fixture 把卡片调到满意，再接真后端。因为行程卡片的样式调整是前端工作量最大的一块，反复等 LLM 生成太浪费时间。

### 12.3 调试技巧

| 想看的 | 怎么做 |
|---|---|
| WS 收到了什么帧 | `ws_client._on_frame` 开头加 `print(frame["type"], frame.get("data"))` |
| 流式节流有没有生效 | 在 `_flush_buffer` 里计数，观察每秒刷新次数 |
| 卡片为什么没显示 | 打印 `itinerary` 是否为 `None`；看后端日志有没有解析失败 |
| 后端返回了什么 | 在 `api_client._request` 里打印 `resp.status_code` 与 body |
| 会话不刷新 | 检查 `updated_at` 是否被后端更新（改标题、发消息都应更新） |

### 12.4 后端没起来时的表现

| 现象 | 原因 |
|---|---|
| 登录页点了没反应 | 后端 8000 没起，`httpx.ConnectError` |
| 登录成功但聊天一直没回复 | WS 连不上，检查 `TPA_BACKEND_BASE_URL` 是否写错（注意不要带尾部 `/`） |
| 一直"连接已断开" | WS 地址应形如 `ws://127.0.0.1:8000/api/v1/ws/chat`，从 `http://` 换算是 `ws://` |
| 上传文档报 403 | 用的不是 root 账号 |

---

**文档结束。**

> 前端只消费后端契约，不定义契约。发现字段不够用，先提给后端改 [BACKEND.md](BACKEND.md)，再改前端。
