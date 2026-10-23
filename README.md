# 出行计划智能助手（后端 + 前端）

对话式出行规划助手：问一句 → 查天气 / 查地点 → 出带卡片的行程 → 数据全存下来。

> **本仓库包含两部分**
> - **后端**（本文档主体）：`backend/`、`mcp_servers/`、`scripts/`
> - **前端**：`frontend/`（NiceGUI，服务端渲染），启动方式见 [frontend/README.md](frontend/README.md)

**接口与数据契约以 [`docs/BACKEND.md`](docs/BACKEND.md) 为唯一来源**，本 README 只讲"怎么跑"。
配套文档：[前端设计](docs/FRONTEND.md)　[测试](docs/TESTING.md)　[索引](docs/DEVELOPMENT.md)

| 项 | 内容 |
|---|---|
| 技术栈 | Python 3.11+ / FastAPI / LangChain + LangGraph / MCP / SQLite / Chroma |
| 接口 | 20 个（含 1 个 WebSocket） |
| 数据表 | 4 张 |
| MCP 工具 | 5 个（weather 2 + place 3）+ 1 个原生工具 |
| 环境变量 | 23 项（文档 19 项 + 向量化 4 项） |

---

## 0. 10 秒打开（服务已经跑起来之后）

后端**没有页面**，它是纯 API。你能"打开"的是三个地址：

| 地址 | 是什么 | 怎么用 |
|---|---|---|
| <http://127.0.0.1:8000/docs> | **交互式接口文档**（Swagger UI） | 点开就能点"Try it out"直接调接口，不用写代码 |
| <http://127.0.0.1:8000/healthz> | 探活 | 返回 `{"status":"ok"}` 就说明进程活着 |
| <http://127.0.0.1:8000/readyz> | 依赖自检 | 同时看 DB、两个 MCP Server、RAG，以及**当前生效的配置指纹**（key 是否读对，一眼就看出来） |

> **改完 `.env` 必须重启服务**：`--reload` 只盯 `.py` 文件，`.env` 只在进程启动时读一次。
> 不确定生效没有？打开 `/readyz`，`checks.config` 里的 `amap_key` / `llm_key` 是脱敏指纹（前 6 位 + 长度）。

### 在 /docs 里跑通第一个接口

1. 浏览器打开 <http://127.0.0.1:8000/docs>
2. 展开 `POST /api/v1/auth/login` → **Try it out**，Request body 填：
   ```json
   { "username": "root", "password": "你的root密码" }
   ```
   （密码就是 `.env` 里 `TPA_ROOT_PASSWORD` 的值）→ **Execute**。复制响应里 `data.token` 那一长串（`eyJ...`）。
3. 页面最上方点 **Authorize** 🔓，把 token 粘进去（**不要**加 `Bearer ` 前缀，Swagger 会自己加）→ Authorize → Close。
4. 之后所有需要登录的接口都能直接调了。试试：
   - `POST /api/v1/conversations`（body 留空）→ 拿一个 `id`
   - `GET /api/v1/tools` → 看 6 个工具和两个 MCP Server 状态
   - `POST /api/v1/tools/weather_now/invoke`，body `{"args":{"city":"杭州"}}` → 看工具返回的真实 JSON
   - `POST /api/v1/conversations/{id}/messages`，body `{"content":"这周末去杭州两天"}` → 完整跑一轮对话（需要真 LLM Key）

> `/docs` 里调不到 WebSocket（那是 `/api/v1/ws/chat`，要用前端或 `wscat`/Python 脚本）。

### 用命令行调（不打开浏览器也行）

> ⚠️ **PowerShell 5.1 的坑**：`Invoke-RestMethod -ContentType "application/json"` 不带 charset 时，
> 请求体是按 **ASCII** 编码的，中文会变成 `?`——高德随即返回"查不到城市"。
> 测中文一定要写 `-ContentType "application/json; charset=utf-8"`，或者干脆用 `curl` / Python。
> 这不是服务的问题，但极容易被误判成"中文编码坏了"。

```powershell
# 1. 登录拿 token（注意 charset=utf-8；密码填 .env 里的 TPA_ROOT_PASSWORD）
$r = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/auth/login -Method Post `
     -ContentType "application/json; charset=utf-8" -Body '{"username":"root","password":"你的root密码"}'
$h = @{ Authorization = "Bearer $($r.data.token)" }

# 2. 建会话 -> 发一条消息
$conv = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/conversations -Method Post -Headers $h
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/conversations/$($conv.data.id)/messages" `
  -Method Post -Headers $h -ContentType "application/json; charset=utf-8" `
  -Body '{"content":"这周末去杭州两天，预算 1500"}'
```

```bash
# curl 版本
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" -d '{"username":"root","password":"你的root密码"}'
# 把返回的 token 填进来
curl -s http://127.0.0.1:8000/api/v1/tools -H "Authorization: Bearer <token>"
```

### 下次自己启动

```bash
uvicorn backend.main:app --reload --port 8000
```

看到这两行才算真的起来了（MCP 子进程是后端的命门）：

```
INFO  tpa.mcp_manager | MCP Server weather 已连接，发现 2 个工具: ...
INFO  tpa.mcp_manager | MCP Server place 已连接，发现 3 个工具: ...
INFO  Uvicorn running on http://127.0.0.1:8000
```

日志里出现 `disabled` / `degraded` 就去 `/readyz` 看哪个 Server 掉了，或翻 `data/logs/{weather,place}-mcp.log`。

---

## 1. 快速开始

```bash
# 1. 装依赖（版本已实测钉死）
python -m pip install -r requirements.txt

# 2. 配置：填 4 个必填项
cp .env.example .env
#   TPA_JWT_SECRET     >= 32 字符的随机串
#   TPA_ROOT_PASSWORD  >= 8 位
#   TPA_LLM_API_KEY    DeepSeek Key
#   TPA_AMAP_KEY       高德「Web 服务」类型 Key

# 3. 建表 + 创建 root（幂等）
python scripts/init_db.py

# 4. 冒烟：4 步全过再往下
python scripts/smoke.py

# 5. 起服务
uvicorn backend.main:app --reload --port 8000
```

**前端（可选，另一个终端；后端要先起好）**

```bash
python -m pip install -r requirements-frontend.txt
python -m frontend.main            # 打开 http://127.0.0.1:8080
```

> 没有后端也能调 UI 样式：`$env:TPA_MOCK="1"; python -m frontend.main`（PowerShell）。
> 细节（环境变量、目录、交互实现）见 [frontend/README.md](frontend/README.md)。
> 注意 `requirements-frontend.txt` 把 NiceGUI 限在 `<3`：3.x 要求 `starlette>=1.3`，会顶掉后端钉死的版本。

打开 <http://127.0.0.1:8000/docs> 可以直接试 19 个 REST 接口（WebSocket 除外），
<http://127.0.0.1:8000/healthz> 探活、<http://127.0.0.1:8000/readyz> 查 DB 与 MCP。

**冒烟输出的四种状态**

| 输出 | 含义 |
|---|---|
| `1/4 数据库 ... OK (4 张表，root 已存在)` | 建表与种子 root 正常 |
| `2/4 MCP Servers ... OK (weather 2 工具 / place 3 工具)` | 两个子进程起来了；失败时会打印子进程 stderr 最后 20 行 |
| `3/4 高德 API ... OK (杭州市 22℃ 多云，271ms)` | Key 与网络都通；失败按 infocode 给提示 |
| `4/4 LLM 调用 ... OK (模型调用了工具，N 字输出)` | 模型支持 function calling 且真的调了工具 |

> 第 4 步只断言**行为**（有没有发起工具调用），不断言回答内容。

---

## 2. 目录结构

```
Travel Planning Agent/
├─ requirements.txt
├─ .env.example          # 23 项配置模板（.env 不入库）
├─ data/                 # 运行时生成，不入库
│  ├─ app.db             # SQLite（WAL）
│  ├─ uploads/           # RAG 原始文件
│  ├─ chroma/            # 向量索引
│  └─ logs/              # MCP 子进程 stderr（排障用）
├─ backend/
│  ├─ main.py            # FastAPI 应用、路由挂载、lifespan
│  ├─ config.py          # Settings（23 项，缺必填项启动即失败）
│  ├─ db.py              # engine / session / create_all / 种子 root
│  ├─ models.py          # 4 张表 ORM
│  ├─ schemas.py         # 请求模型 + 行程 Schema + 出参序列化
│  ├─ security.py        # argon2id + JWT
│  ├─ deps.py            # current_user / require_root
│  ├─ errors.py          # ApiError + 22 个错误码 + 全局异常处理器
│  ├─ api/               # auth / conversations / chat(WS) / tools / rag / admin
│  ├─ services/          # conversation / chat / rag / export / mcp_manager
│  └─ agent/             # llm / prompts / tools / itinerary / graph
├─ mcp_servers/
│  ├─ common/            # envelope（统一信封）+ amap（高德适配）
│  ├─ weather/           # weather_now / weather_forecast
│  └─ place/             # place_search / geo_geocode / route_plan
└─ scripts/
   ├─ init_db.py
   └─ smoke.py

frontend/                # NiceGUI 前端（详见 frontend/README.md）
├─ main.py               # ui.run + "/" 路由
├─ config.py             # 环境变量与 WS 地址（不 import backend）
├─ api_client.py         # httpx 封装 + MockApiClient
├─ ws_client.py          # websockets 封装 + MockChatSocket
├─ state.py / theme.py / ui_utils.py
├─ mock_store.py / mock_data.py   # TPA_MOCK=1 时的写死数据
├─ components/           # shell / conversation_list / message_bubble / itinerary_card /
│                        # tool_call_panel / thinking_bar / dialogs / markdown_export
└─ pages/                # login / chat / knowledge / users
```

**依赖方向（Code Review 只看这一条）**

```
api/ ──► services/ ──► agent/ , mcp_manager , models , schemas
             └──► db , security , errors , config

✗ api/ 禁止 import agent/ 或 mcp_manager
✗ mcp_servers/ 与 backend/ 禁止互相 import
✗ frontend/ 禁止 import backend/（只走 HTTP / WebSocket）
```

---

## 3. 架构要点

三条不可破坏的约束：

| 约束 | 在这里怎么落实 |
|---|---|
| 工具跑在独立进程，经 MCP 通信 | `services/mcp_manager.py` 用 `stdio_client` + `ClientSession` 拉起两个子进程；每个 Server 的会话固定跑在**一个专属后台任务**里，调用走队列 —— 既串起同一条 stdio 管道，也避开 anyio cancel scope 跨任务的老问题 |
| Agent 只 yield 事件，不碰 WebSocket | `agent/graph.py::run()` 是纯异步生成器，只 yield `tool_start / tool_end / token / itinerary / done`；WS 层（`api/chat.py`）和 REST 层（`services/chat_service.py`）都是它的消费者 |
| `api/` 不许直接 import `agent/` | 业务全在 `services/` 收口，`api/` 只做校验、鉴权、封装信封 |

两个容易被写错、这里已经处理掉的点：

- **生成与发送分离**：WS 收到 `message` 后只 `create_task` 起后台生成任务，再用一个 pump 任务把事件队列推给前端。**用户关掉页面，回复照样生成完并落库。**
- **会话锁**：`asyncio.Lock`，进程内 `dict[str, Lock]`。"检查 + `await acquire()`"之间没有让出点，不会出现两个任务同时拿到锁；`ux_msg_seq` 唯一索引是最后一道防线（撞了转成 `CONV_BUSY`）。

---

## 4. 配置（23 项，前缀 `TPA_`）

> 文档原定 19 项；向量化改成 API 后 **+4 项**（`TPA_RAG_EMBEDDING_PROVIDER` / `_BASE_URL` / `_API_KEY` / `_DIM`），
> 见第 8 节差异说明。

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `TPA_ENV` | 否 | `dev` | `dev` 时开 SQL 回显 |
| `TPA_PORT` | 否 | `8000` | —— |
| `TPA_DATA_DIR` | 否 | `./data` | 库、上传、Chroma 都在这里 |
| `TPA_JWT_SECRET` | **是** | —— | HS256 密钥，≥32 字符 |
| `TPA_JWT_EXPIRE_HOURS` | 否 | `12` | access token 有效期 |
| `TPA_ROOT_USERNAME` | 否 | `root` | 种子 root 用户名 |
| `TPA_ROOT_PASSWORD` | **是** | —— | 首次启动创建；已存在时不覆盖 |
| `TPA_ALLOW_REGISTER` | 否 | `true` | 关闭后只有 root 能建号 |
| `TPA_LLM_BASE_URL` | 否 | DeepSeek | 换 OpenAI/Ollama 改这里 |
| `TPA_LLM_API_KEY` | **是** | —— | —— |
| `TPA_LLM_MODEL` | 否 | `deepseek-chat` | **不可用 `deepseek-reasoner`**（不支持 function calling，启动会报错） |
| `TPA_LLM_TEMPERATURE` | 否 | `0.3` | —— |
| `TPA_AMAP_KEY` | **是** | —— | 高德 **Web 服务** 类型 Key |
| `TPA_AMAP_TIMEOUT` | 否 | `8` | 秒 |
| `TPA_RAG_ENABLED` | 否 | `true` | 关掉则 `/rag/*` 返 503、不挂检索工具 |
| `TPA_RAG_EMBEDDING_PROVIDER` | 否 | `api` | `api`（调 `/embeddings`）或 `local`（本地 bge-m3，要 torch） |
| `TPA_RAG_EMBEDDING_MODEL` | 否 | `BAAI/bge-m3` | 模型名；`local` 模式下也可填本地目录 |
| `TPA_RAG_EMBEDDING_BASE_URL` | 否 | 硅基流动 | OpenAI 兼容地址，**要带 `/v1`**（代码会拼 `/embeddings`） |
| `TPA_RAG_EMBEDDING_API_KEY` | api 模式**必填** | —— | 缺了能启动，但知识库上传会 503 |
| `TPA_RAG_EMBEDDING_DIM` | 否 | `1024` | 维度校验；换模型必须同步改并清 `data/chroma` |
| `TPA_RAG_CHUNK_SIZE` | 否 | `800` | 字符 |
| `TPA_RAG_TOP_K` | 否 | `5` | 检索条数 |
| `TPA_AGENT_MAX_ITERATIONS` | 否 | `8` | 防死循环 |

密钥只走环境变量，不写代码、不打日志；MCP 子进程通过**环境变量白名单**继承 `TPA_AMAP_KEY`，不用命令行参数。

---

## 5. 接口总览（20 个）

基础路径 `/api/v1`，成功 `{"ok":true,"data":…,"error":null}`，失败 `{"ok":false,"data":null,"error":{code,message}}`。

| 分组 | 接口 | 权限 |
|---|---|---|
| 认证 | `POST /auth/register`、`POST /auth/login` | 🔓 |
| | `GET /auth/me`、`PUT /auth/profile` | 👤 |
| 会话 | `POST /conversations`、`GET /conversations` | 👤 |
| | `PATCH /conversations/{id}`、`DELETE /conversations/{id}` | 🔒 |
| 消息 | `GET /conversations/{id}/messages`、`POST /conversations/{id}/messages` | 🔒 |
| 实时 | `WS /ws/chat` | 帧内认证 |
| 工具 | `GET /tools`、`POST /tools/{name}/invoke` | 👤 |
| 知识库 | `POST /rag/documents`、`POST /rag/documents/from-url`、`GET /rag/documents`、`DELETE /rag/documents/{id}`、`GET /rag/search` | 👑 |
| 用户管理 | `GET /admin/users`、`PATCH /admin/users/{id}` | 👑 |

**越权一律 404**：访问别人的会话返回 `NOT_FOUND`，不是 `FORBIDDEN`。root 也不因角色获得数据豁免。

### WebSocket 帧

上行 `auth` / `message` / `cancel`；下行 `auth_ok` / `tool`（`phase: start|end`）/ `token`（增量）/ `itinerary` / `done`（唯一终态）/ `error`。
关闭码：`4001` 认证失败、`4002` 帧格式错、`1011` 服务端异常。

---

## 6. RAG（向量化走 API）

**把文本变成向量的模型：`BAAI/bge-m3`，1024 维，调 OpenAI 兼容的 `/embeddings` 接口。**
不用装 torch、不用下 2.3 GB 权重，只要一个 API Key。

### 6.1 申请 Key 与填配置

默认指向**硅基流动**（模型名与本地模式完全一致，维度也是 1024，检索逻辑一行不用改）：

```ini
TPA_RAG_EMBEDDING_PROVIDER=api
TPA_RAG_EMBEDDING_MODEL=BAAI/bge-m3
TPA_RAG_EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
TPA_RAG_EMBEDDING_API_KEY=sk-你申请到的key        # ★ 只需要改这一行
TPA_RAG_EMBEDDING_DIM=1024
```

也可以换成**阿里百炼**（同样 1024 维，OpenAI 兼容模式）：

```ini
TPA_RAG_EMBEDDING_MODEL=text-embedding-v3
TPA_RAG_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
TPA_RAG_EMBEDDING_API_KEY=sk-你的百炼key
TPA_RAG_EMBEDDING_DIM=1024
```

> 换服务商只是改这两行 + Key，**不需要动代码**。但换**维度**不同的模型（比如智谱 `embedding-3` 是 2048）时，
> 必须同步改 `TPA_RAG_EMBEDDING_DIM` 并**清空 `data/chroma`**，否则旧向量维度不匹配。

改完 `.env` **必须重启服务**（`.env` 只在启动时读一次；`--reload` 只盯 `.py`）。
启动日志会打印一行，确认读对了：

```
INFO  tpa.main | RAG 向量化：provider=api model=BAAI/bge-m3 dim=1024 base_url=https://api.siliconflow.cn/v1
```

或者直接看 <http://127.0.0.1:8000/readyz> → `checks.rag`：`provider` / `model` / `dim` / `configured`。

### 6.2 用起来

```bash
# 上传（root 权限；multipart）
curl -X POST http://127.0.0.1:8000/api/v1/rag/documents \
  -H "Authorization: Bearer $ROOT_TOKEN" \
  -F "file=@广州必玩.md" -F "title=广州必玩景点与预约须知"

# 看切得对不对：响应里的 chunk_count + chunk_preview（前 3 块各 100 字）

# 直接检索（最能看出效果）
curl "http://127.0.0.1:8000/api/v1/rag/search?q=广州塔门票怎么预约&top_k=5" \
  -H "Authorization: Bearer $ROOT_TOKEN"
```

`hits` 非空且 `score > 0.3` 就算通；`hits: []` 表示知识库里确实没有，**不是错误**。
检索效果不好怎么调（阈值、块大小），见 [`docs/BACKEND.md` 第 17.8 节](docs/BACKEND.md)。

### 6.3 老文档要重传

改造前入库失败的历史文档（`status=failed`）不会自己好，删掉重传即可：

```powershell
# 列出所有文档，拿 id
curl http://127.0.0.1:8000/api/v1/rag/documents -H "Authorization: Bearer $ROOT_TOKEN"
# 删掉失败的，再重新上传
curl -X DELETE http://127.0.0.1:8000/api/v1/rag/documents/<id> -H "Authorization: Bearer $ROOT_TOKEN"
```

### 6.4 还想本地跑（离线场景）

```powershell
python -m pip install "sentence-transformers>=3.0"
# 然后把 TPA_RAG_EMBEDDING_PROVIDER 改成 local
```

首次会下载 bge-m3 权重（约 2.3 GB）。两条路的向量在语义上一致（同一模型），可以互换，但**同一份 Chroma 里不要混**。

> JSON 检索命中会回库校验 `rag_documents.status='ready'`：**SQLite 是权威源，Chroma 只是索引**，
> 已删文档的内容不会被喂给模型。

---

## 7. 排障

| 现象 | 原因 / 怎么办 |
|---|---|
| MCP Server 起不来，日志有 JSON 解析错 | 工具里用了 `print()`。stdout 是 JSON-RPC 通道，日志只能写 stderr |
| 工具总返回 `TOOL_UNAVAILABLE` | 子进程没起来。看 `data/logs/weather-mcp.log`、`data/logs/place-mcp.log` 或 `/readyz` |
| `/tools` 里 `degraded=true` | 有 Server 不可用，Agent 能力受限；对话仍可用（提示词会自动追加"不要编造天气/地点"） |
| 高德返回全空 / `UPSTREAM_AUTH_FAILED` | Key 类型不是「Web 服务」，或没开对应 API 权限 |
| 模型不调工具、直接编答案 | 提示词约束不够强，或模型不支持 function calling（**别用 `deepseek-reasoner`**） |
| 界面一直"生成中" | 服务被重启了。启动自愈会把 `pending` 标 `failed`，刷新即可 |
| 行程卡片不出现 | 模型没输出 ` ```json ` 代码块。看日志有没有"itinerary 解析失败"；文本不会丢 |
| 首次上传文档卡很久 | `local` 模式在下载/加载 BGE-M3（2.3 GB）；`api` 模式不会，只有网络慢 |
| `RAG_DISABLED`：未配置 `TPA_RAG_EMBEDDING_API_KEY` | 只影响知识库，对话正常。填 Key 后**重启** |
| `RAG_DISABLED`：HTTP 401/403 | Key 错、或无该模型权限。核对 `TPA_RAG_EMBEDDING_API_KEY` 与服务商控制台 |
| `RAG_DISABLED`：HTTP 404 | `TPA_RAG_EMBEDDING_BASE_URL` 少了 `/v1`，或模型名拼错 |
| `RAG_DISABLED`：向量维度是 X，配置是 Y | 换过模型：改 `TPA_RAG_EMBEDDING_DIM`，并**清空 `data/chroma`** 后重传 |
| 删除会话后消息还在 | 不该出现：service 里是显式两步删除，不依赖 `PRAGMA foreign_keys` |

---

## 8. 与文档的三处显式差异

改文档前先看这三条，都是"照文档写反而跑不通 / 已经演进"的地方：

1. **`messages.status` 的 CHECK 约束补了 `pending`。**
   `BACKEND.md` 6.6 的 DDL 只写了 `completed/failed/cancelled`，但 10.1 要求 assistant 占位用
   `status=pending` 落库、18.2 的启动自愈要把 `pending` 改成 `failed`。不补 `pending`，
   占位就写不进去，界面的"生成中"也无从恢复。见 `backend/models.py::Message`。

2. **`scripts/smoke.py` 按 `TESTING.md` 第 3 章的四步输出**（数据库 → MCP Servers → 高德 API → LLM 调用），
   比 `BACKEND.md` 第 2 章的"一次 LLM 调用 + 一次 MCP 工具调用"更细，两者目标一致。
   第 2 步失败时会打印子进程 stderr 的最后 20 行 —— 否则你只会看到一个 `TOOL_UNAVAILABLE`。

3. **向量化后端改成可配置，默认走 API**（原文档 17.5 只写了本地 `sentence-transformers`）。
   `TPA_RAG_EMBEDDING_PROVIDER=api|local` + `_BASE_URL` / `_API_KEY` / `_DIM` 四个新配置项，
   是为了不装 torch、不下载 2.3 GB 权重也能用 RAG；模型仍是 `BAAI/bge-m3`、
   维度仍是 1024，所以 17.5 的其余结论（归一化、批量、不加 query 前缀、串行）全部照旧。
   `local` 模式保留，行为与原文档一致。

---

## 9. 已跑通的验证

本机（Windows + Python 3.13）实测结果：

| 验证项 | 结果 | 怎么验的 |
|---|---|---|
| 建表 + 种子 root（幂等） | ✅ | `python scripts/init_db.py` 跑两遍，第二遍打印"root 已存在，跳过" |
| MCP 两个子进程 + 5 个工具 | ✅ | `/readyz` 与 `/tools`：weather 2 + place 3，`degraded=false` |
| 19 个 REST 接口 + 信封/错误码/越权 | ✅ 37/37 | 逐接口脚本，覆盖 409 重名、401、403、404 越权、400 参数、503/201 失败入库 |
| WebSocket 认证/坏帧/CONV_BUSY/落库 | ✅ 10/10 | 含"发完就断连，消息仍落库"与"第二句立刻收到 CONV_BUSY" |
| 行程 JSON 解析与 7 条自动修正 | ✅ 11/11 | 跳日补空日、时段倒置置空、weekday 重算、预算偏差、天气以工具为准 |
| RAG 流水线（解析/分块/Chroma/检索/删除/SSRF） | ✅ 14/14 | 用确定性假向量替代模型 |
| **API 向量化（分批 / 归一化 / 维度校验 / 缺 key）** | ✅ 11/11 | 起一个假的 OpenAI 兼容 `/v1/embeddings`：17 块 → 2 批 `[10,7]`、请求带 Bearer、`score` 命中、删干净；缺 key 与维度不符都给出可操作提示 |
| 启动自愈（pending → failed） | ✅ | 造一条 pending 消息，重启后状态变 failed 且补占位文本 |
| LLM 真实调用 / 高德真实数据 | ✅ | 填上真 Key 后 `scripts/smoke.py` 4/4；一整轮对话出 9 项/6 项的行程卡片 |
| 真实向量化服务（硅基流动 / 百炼） | ⚠️ 待 Key | 代码路径已用假服务验完，填上 `TPA_RAG_EMBEDDING_API_KEY` 后即通 |

---

## 10. 下一步

- 接口自动化测试：`tests/` 目录的设计（fixture、Mock 策略、20 个用例）见 [`docs/TESTING.md` 第 4 章](docs/TESTING.md)。
- 前端：NiceGUI 页面与交互见 [`docs/FRONTEND.md`](docs/FRONTEND.md)。
- 上线前补齐顺序（限流、refresh token、审计日志…）见 [`docs/BACKEND.md` 18.7](docs/BACKEND.md)。
