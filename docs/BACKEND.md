# 出行计划智能助手 —— 后端开发文档

| 项 | 内容 |
|---|---|
| 适用范围 | 后端工程师 |
| 版本 | Demo v1.0 |
| 技术栈 | Python 3.11 / FastAPI / LangChain + LangGraph / MCP / SQLite / Chroma |
| 代码量估算 | 约 1800–2400 行 |
| 配套文档 | [前端](FRONTEND.md)　[测试](TESTING.md) |

> **本文档是接口与数据契约的唯一来源。** 前端文档只描述"怎么调"，不重复定义字段；字段有歧义时以本文档为准。

---

## 目录

- [1. 后端职责与边界](#1-后端职责与边界)
- [2. 技术选型](#2-技术选型)
- [3. 架构与进程模型](#3-架构与进程模型)
- [4. 目录结构与依赖方向](#4-目录结构与依赖方向)
- [5. 配置](#5-配置)
- [6. 数据模型](#6-数据模型)
- [7. 接口规范总则](#7-接口规范总则)
- [8. 认证接口](#8-认证接口)
- [9. 会话与消息接口](#9-会话与消息接口)
- [10. 非流式发消息](#10-非流式发消息)
- [11. WebSocket 对话](#11-websocket-对话)
- [12. 工具接口](#12-工具接口)
- [13. 知识库接口](#13-知识库接口)
- [14. 用户管理接口](#14-用户管理接口)
- [15. MCP 工具契约](#15-mcp-工具契约)
- [16. Agent 设计](#16-agent-设计)
- [17. RAG 实现](#17-rag-实现)
- [18. 启动与运维](#18-启动与运维)

---

## 1. 后端职责与边界

### 1.1 后端负责

| # | 职责 |
|---|---|
| R1 | 认证与权限：注册、登录、签发 JWT、`root`/`user` 两角色校验 |
| R2 | 会话与消息持久化：SQLite 落库，重启不丢 |
| R3 | Agent 编排：装配上下文、挂工具、跑 ReAct 图、产出结构化行程 |
| R4 | MCP 客户端：拉起两个工具子进程、发现工具、调用并收结果 |
| R5 | RAG：文档解析、分块、嵌入、Chroma 检索、引用回填 |
| R6 | 流式推送：WebSocket 逐字输出 + 工具调用过程 |
| R7 | 行程导出：生成 Markdown 文件流 |
| R8 | 用户画像读写与注入 |

### 1.2 后端**不**负责

| 不负责 | 归属 |
|---|---|
| 页面渲染、表单校验、交互状态 | 前端 |
| 直接拼高德 URL | `mcp_servers/`（统一经 MCP 工具） |
| 工具数据源的字段映射 | `mcp_servers/common/amap.py` |
| 不做限流、熔断、审计、监控、多实例 | Demo 明确不做 |

### 1.3 三条不可破坏的架构约束

| 约束 | 为什么 |
|---|---|
| **工具跑在独立进程**，经 MCP 通信 | 工具崩了主服务不死；工具可单独测；换数据源只改 `mcp_servers/` |
| **Agent 只 yield 事件，不碰 WebSocket** | WS 层、非流式接口都是事件的消费者；断连后生成仍可继续 |
| **`api/` 不许直接 import `agent/` 或 `mcp_manager`** | 业务必须在 `services/` 收口，否则换 Agent 会牵一发动全身 |

---

## 2. 技术选型

| 层 | 选型 | 版本约束 |
|---|---|---|
| Web 框架 | FastAPI + Uvicorn | `fastapi>=0.115` |
| 数据校验 | Pydantic v2 + pydantic-settings | `>=2.9` |
| ORM | SQLAlchemy 2.0 async + aiosqlite | `>=2.0.35` |
| 鉴权 | PyJWT（HS256）+ pwdlib[argon2] | `pyjwt>=2.9`、`pwdlib[argon2]>=0.2` |
| Agent | LangChain + LangGraph `create_react_agent` | `langchain>=0.3`、`langgraph>=0.2` |
| 模型接入 | langchain-openai（兼容协议） | `>=0.2` |
| MCP | `mcp` + `langchain-mcp-adapters` | `mcp>=1.2`、`langchain-mcp-adapters>=0.1` |
| 向量库 | chromadb | `>=0.5` |
| 嵌入 | sentence-transformers + BGE-M3 | `>=3.0` |
| 文档解析 | pypdf、python-docx、trafilatura、beautifulsoup4 | —— |
| 出站 HTTP | httpx | `>=0.27` |
| 导出 | 标准库字符串模板（不引额外库） | —— |

**DeepSeek 两个注意点**

1. 走 OpenAI 兼容层：`ChatOpenAI(base_url="https://api.deepseek.com", model="deepseek-chat", api_key=...)`。DeepSeek 没有独立 LangChain 包，兼容层最省事。
2. **不要用 `deepseek-reasoner`**，它不支持 function calling，而本项目核心就是工具调用。`llm.py` 里加一个断言：模型名含 `reasoner` 就启动失败。

> ⚠️ **M0 必做**：`langchain-mcp-adapters` 与 `mcp` 迭代很快，`MultiServerMCPClient` 的构造参数可能随小版本变化。先写 `scripts/smoke.py` 跑通"一次 LLM 调用 + 一次 MCP 工具调用"，把实际可用版本号钉死在 `requirements.txt`，再写业务代码。

---

## 3. 架构与进程模型

```
┌───────────────────────────────────────┐
│ 前端进程 NiceGUI :8080（独立部署）      │
└──────────────┬────────────────────────┘
               │ HTTP + WebSocket
┌──────────────▼────────────────────────┐
│ 后端进程 FastAPI :8000                 │
│                                       │
│  api/       路由：鉴权、校验、封装响应   │
│  services/  业务：会话、消息、RAG、导出  │
│  agent/     LangGraph ReAct + 提示词    │
│  mcp_manager  拉起并管理工具子进程      │
│                                       │
│  SQLite  data/app.db                  │
│  Chroma  data/chroma                  │
└──────────────┬────────────────────────┘
               │ stdio / JSON-RPC
     ┌─────────┴──────────┐
┌────▼───────┐    ┌───────▼──────┐
│weather-mcp │    │  place-mcp   │
│ 2 个工具    │    │  3 个工具     │
└────┬───────┘    └──────┬───────┘
     └────────┬──────────┘
              │ HTTPS
     ┌────────▼─────────┐
     │  高德 Web 服务 API │
     └──────────────────┘
```

### 3.1 一次对话的完整链路

```
前端 WS
  │ message{conversation_id, content}
  ▼
chat.py           校验归属、判断会话是否正在生成
  ▼
chat_service      ① 落库 user 消息  ② 建 assistant 占位  ③ 装配上下文
  ▼
agent.run()       ④ 挂工具  ⑤ 跑 ReAct 图
  │                 ├─ yield tool_start  → WS 推送"正在查天气"
  │                 ├─ (MCP 调用)        → weather-mcp → 高德
  │                 ├─ yield tool_end    → WS 推送结果摘要
  │                 ├─ yield token ×N    → WS 逐字推送
  │                 └─ yield itinerary   → WS 推送行程
  ▼
chat_service      ⑥ 落库 assistant 消息（含 itinerary/citations/tool_calls）
  ▼
前端 WS           ⑦ 收到 done，用完整文本对齐
```

**关键点：生成任务是后台任务，与 WS 连接解耦。** 前端断网/切标签页不会中断生成，重连后调 `GET /messages` 补拉即可看到完整结果。

### 3.2 会话并发控制

同一会话同时只允许一个生成任务。实现：进程内 `dict[str, asyncio.Lock]`。

| 情况 | 行为 |
|---|---|
| 会话正在生成，又来新消息 | 回 `CONV_BUSY`（WS 走 error 帧，REST 走 409），连接不断 |
| 用户取消 | 取消 asyncio task，已生成内容以 `cancelled` 落库，照常发 `done` |
| 进程重启 | 启动时把所有 `status='pending'` 的消息改 `failed` |

---

## 4. 目录结构与依赖方向

```
Travel Planning Agent/
├─ requirements.txt
├─ .env.example
├─ .gitignore
├─ README.md
├─ data/                       # 运行时生成，不入库
│  ├─ app.db
│  ├─ uploads/
│  └─ chroma/
├─ backend/
│  ├─ main.py                  # FastAPI 应用、路由挂载、lifespan（拉起 MCP、启动自愈）
│  ├─ config.py                # Settings
│  ├─ db.py                    # engine / session / create_all
│  ├─ models.py                # 4 张表 ORM
│  ├─ schemas.py               # Pydantic 请求/响应 + 行程 Schema
│  ├─ security.py              # 密码哈希 + JWT 编解码
│  ├─ deps.py                  # current_user / require_root
│  ├─ errors.py                # ApiError + 全局异常处理器
│  ├─ api/
│  │  ├─ auth.py
│  │  ├─ conversations.py
│  │  ├─ chat.py               # WebSocket
│  │  ├─ tools.py
│  │  ├─ rag.py
│  │  └─ admin.py
│  ├─ services/
│  │  ├─ conversation_service.py
│  │  ├─ chat_service.py       # 装配 → 跑 Agent → 落库
│  │  ├─ rag_service.py
│  │  ├─ export_service.py     # 可选：前台导出由前端本地生成，这里只留作脚本用
│  │  └─ mcp_manager.py
│  └─ agent/
│     ├─ llm.py                # LLMFactory
│     ├─ graph.py              # ReAct 图
│     ├─ prompts.py
│     ├─ tools.py              # search_knowledge_base
│     └─ itinerary.py          # 解析与修正
├─ mcp_servers/
│  ├─ common/
│  │  ├─ envelope.py
│  │  └─ amap.py
│  ├─ weather/server.py
│  └─ place/server.py
└─ scripts/
   ├─ init_db.py
   └─ smoke.py
```

**依赖方向（Code Review 只看这一条）**

```
api/  ──►  services/  ──►  agent/ , mcp_manager , models , schemas
              │
              └──►  db , security , errors , config

✗ api/ 禁止 import agent/ 或 mcp_manager
✗ mcp_servers/ 与 backend/ 禁止互相 import
✗ frontend/ 禁止 import backend/
```

### 4.1 各模块职责

| 模块 | 职责 | 不做什么 |
|---|---|---|
| `api/*` | 入参校验、鉴权依赖、调 service、封装信封 | 不写业务逻辑、不直接碰 ORM |
| `services/*` | 业务编排、事务边界、落库 | 不处理 HTTP |
| `agent/*` | LLM 调用、工具编排、结构化输出 | 不知道 WS 存在，不写库 |
| `mcp_manager` | 子进程生命周期、工具发现、调用 | 不做字段映射（那是 Server 的事） |
| `mcp_servers/*` | 高德适配、字段映射、统一信封 | 不鉴权、不写库、不感知用户 |
| `models/schemas` | 表结构、传输结构 | 不含逻辑 |

---

## 5. 配置

全部走 `.env`，前缀 `TPA_`。**19 项**，缺必填项启动即报错退出。

```ini
# ---- 应用 ----
TPA_ENV=dev
TPA_PORT=8000
TPA_DATA_DIR=./data

# ---- 安全 ----
TPA_JWT_SECRET=
TPA_JWT_EXPIRE_HOURS=12
TPA_ROOT_USERNAME=root
TPA_ROOT_PASSWORD=
TPA_ALLOW_REGISTER=true

# ---- 模型 ----
TPA_LLM_BASE_URL=https://api.deepseek.com
TPA_LLM_API_KEY=
TPA_LLM_MODEL=deepseek-chat
TPA_LLM_TEMPERATURE=0.3

# ---- 高德 ----
TPA_AMAP_KEY=
TPA_AMAP_TIMEOUT=8

# ---- RAG ----
TPA_RAG_ENABLED=true
TPA_RAG_EMBEDDING_MODEL=BAAI/bge-m3
TPA_RAG_CHUNK_SIZE=800
TPA_RAG_TOP_K=5

# ---- Agent ----
TPA_AGENT_MAX_ITERATIONS=8
```

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `TPA_ENV` | 否 | `dev` | `dev` 时开 SQL 回显与详细报错 |
| `TPA_PORT` | 否 | `8000` | —— |
| `TPA_DATA_DIR` | 否 | `./data` | 库、上传、Chroma 都在这里 |
| `TPA_JWT_SECRET` | **是** | —— | HS256 密钥，≥32 字符 |
| `TPA_JWT_EXPIRE_HOURS` | 否 | `12` | access token 有效期 |
| `TPA_ROOT_USERNAME` | 否 | `root` | 种子 root 用户名 |
| `TPA_ROOT_PASSWORD` | **是** | —— | 首次启动创建；**已存在时不覆盖** |
| `TPA_ALLOW_REGISTER` | 否 | `true` | 关闭后只有 root 能建号 |
| `TPA_LLM_BASE_URL` | 否 | DeepSeek | 换 OpenAI/Ollama 改这里 |
| `TPA_LLM_API_KEY` | **是** | —— | —— |
| `TPA_LLM_MODEL` | 否 | `deepseek-chat` | 不可用 `deepseek-reasoner` |
| `TPA_LLM_TEMPERATURE` | 否 | `0.3` | 行程要稳，别太高 |
| `TPA_AMAP_KEY` | **是** | —— | 高德 **Web 服务** 类型 Key |
| `TPA_AMAP_TIMEOUT` | 否 | `8` | 秒 |
| `TPA_RAG_ENABLED` | 否 | `true` | 关掉则 `/rag/*` 返 503、不挂检索工具 |
| `TPA_RAG_EMBEDDING_MODEL` | 否 | `BAAI/bge-m3` | 也可填本地目录 |
| `TPA_RAG_CHUNK_SIZE` | 否 | `800` | 字符 |
| `TPA_RAG_TOP_K` | 否 | `5` | 检索条数 |
| `TPA_AGENT_MAX_ITERATIONS` | 否 | `8` | 防死循环 |

**三条硬规矩**

1. `.env` 不进仓库，只提交 `.env.example`。
2. 密钥只走环境变量，不写代码、不打日志、不放 `repr`。
3. MCP 子进程通过**环境变量白名单**继承 `TPA_AMAP_KEY`，不用命令行参数（防 `ps` 看到）。

---

## 6. 数据模型

**4 张表。** 够用且不冗余——Chroma 里存向量和块文本，SQLite 只存"有哪些文档"。

```
users ──1:N──> conversations ──1:N──> messages
  └──1:N──> rag_documents
```

### 6.1 `users`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | UUID |
| `username` | TEXT UNIQUE | 登录名，3–32 字符 |
| `password_hash` | TEXT | argon2id |
| `role` | TEXT | `root` / `user` |
| `status` | TEXT | `active` / `disabled` |
| `profile` | JSON | 用户画像，默认 `{}`，见 6.5 |
| `created_at` | DATETIME | —— |

### 6.2 `conversations`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | UUID |
| `user_id` | TEXT FK | 属主，`ON DELETE CASCADE` |
| `title` | TEXT | 默认 `新对话`，首条消息后由 LLM 生成，用户可改 |
| `created_at` | DATETIME | —— |
| `updated_at` | DATETIME | 列表排序键 |

### 6.3 `messages`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | UUID |
| `conversation_id` | TEXT FK | `ON DELETE CASCADE` |
| `seq` | INTEGER | 会话内自增，从 1 开始 |
| `role` | TEXT | `user` / `assistant` |
| `content` | TEXT | 正文（Markdown） |
| `status` | TEXT | `completed` / `failed` / `cancelled` |
| `itinerary` | JSON | 结构化行程（仅 assistant，可空），见 16.4 |
| `citations` | JSON | RAG 引用数组（可空） |
| `tool_calls` | JSON | 工具调用摘要 `[{name, args, ok, ms}]` |
| `created_at` | DATETIME | —— |

> 工具调用不单独建表，直接塞进 `tool_calls`。Demo 不需要按工具做统计。

**`seq` 分配规则**：取 `SELECT MAX(seq) FROM messages WHERE conversation_id=?` 再 +1。用户消息与助手占位消息**连续分配两个 seq**（如 5 和 6），这样前端能立刻知道两边的序号。

### 6.4 `rag_documents`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | UUID |
| `title` | TEXT | 文档标题 |
| `source_type` | TEXT | `file` / `url` |
| `filename` | TEXT | 原始文件名或 URL |
| `status` | TEXT | `ready` / `failed`（**同步入库，没有中间态**） |
| `chunk_count` | INTEGER | 分块数 |
| `error` | TEXT | 失败原因 |
| `created_by` | TEXT | 上传者 ID |
| `created_at` | DATETIME | —— |

### 6.5 `profile` 用户画像

用一个 JSON 字段代替独立表，Demo 够用。

```json
{
  "home_city": "上海",
  "budget_level": "comfortable",
  "pace": "balanced",
  "interests": ["历史", "博物馆"],
  "dietary": ["不吃辣"],
  "avoid": ["长途大巴"]
}
```

| 键 | 类型 | 允许值 |
|---|---|---|
| `home_city` | string | ≤20 字符 |
| `budget_level` | string | `economy` / `comfortable` / `luxury` |
| `pace` | string | `relaxed` / `balanced` / `packed` |
| `interests` | string[] | ≤8 项，每项 ≤20 字符 |
| `dietary` | string[] | ≤8 项 |
| `avoid` | string[] | ≤8 项 |

写入时只接受上表键，未知键**忽略**；语义是**整体替换**（不是合并）。

注入 Prompt 时渲染成一句话：

```
常住上海；预算档位：舒适；节奏：适中；兴趣：历史、博物馆；忌口：不吃辣；规避：长途大巴。
```

### 6.6 DDL

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE users (
  id            TEXT PRIMARY KEY,
  username      TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('root','user')),
  status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
  profile       JSON NOT NULL DEFAULT '{}',
  created_at    DATETIME NOT NULL
);

CREATE TABLE conversations (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title      TEXT NOT NULL DEFAULT '新对话',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);
CREATE INDEX ix_conv_user ON conversations(user_id, updated_at DESC);

CREATE TABLE messages (
  id              TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  seq             INTEGER NOT NULL,
  role            TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content         TEXT NOT NULL DEFAULT '',
  status          TEXT NOT NULL DEFAULT 'completed'
                    CHECK (status IN ('completed','failed','cancelled')),
  itinerary       JSON,
  citations       JSON,
  tool_calls      JSON,
  created_at      DATETIME NOT NULL
);
CREATE UNIQUE INDEX ux_msg_seq ON messages(conversation_id, seq);

CREATE TABLE rag_documents (
  id          TEXT PRIMARY KEY,
  title       TEXT NOT NULL,
  source_type TEXT NOT NULL CHECK (source_type IN ('file','url')),
  filename    TEXT,
  status      TEXT NOT NULL DEFAULT 'ready' CHECK (status IN ('ready','failed')),
  chunk_count INTEGER NOT NULL DEFAULT 0,
  error       TEXT,
  created_by  TEXT NOT NULL,
  created_at  DATETIME NOT NULL
);
```

**SQLite 三个必须做的设置**（写在 `db.py` 的 `connect` 事件里）：

```python
PRAGMA journal_mode = WAL       # 读写不互斥
PRAGMA foreign_keys = ON        # 级联删除生效
PRAGMA busy_timeout = 5000      # 写冲突时等 5 秒再报错
```

---

## 7. 接口规范总则

### 7.1 基础约定

| 项 | 规定 |
|---|---|
| 基础路径 | `/api/v1` |
| 编码 | UTF-8 |
| 时间 | UTC，ISO-8601 带 `Z` |
| ID | UUID 字符串 |
| 金额 | 整数分，字段名 `*_cent` |
| 距离/时长 | 整数米 / 秒，`*_m` / `*_s` |
| 坐标 | GCJ-02，字符串 `"经度,纬度"` |
| 鉴权 | `Authorization: Bearer <token>`，除注册登录外全需要 |
| 空值 | 可选字段显式返回 `null`，不省略键 |

### 7.2 响应信封

**成功**

```json
{ "ok": true, "data": { }, "error": null }
```

**失败**

```json
{ "ok": false, "data": null,
  "error": { "code": "AUTH_BAD_CREDENTIALS", "message": "用户名或密码错误" } }
```

| 字段 | 说明 |
|---|---|
| `ok` | 唯一成功标志 |
| `data` | 成功时的数据，失败时恒为 `null` |
| `error` | 失败时 `{code, message}`，成功时恒为 `null` |

> Demo 就三个字段。没有 `request_id`、没有数字业务码、没有 `meta`。

**实现方式**：不要在每个路由里手写字典。用 `errors.py` 里的两个工具函数 + 一个全局异常处理器：

```python
def ok(data=None):            # 成功
    return {"ok": True, "data": data, "error": None}

class ApiError(Exception):    # 业务异常
    def __init__(self, code: str, message: str, status: int = 400): ...

@app.exception_handler(ApiError)
async def handle(req, exc):   # → JSONResponse(status_code=exc.status, ...)
```

路由里只管 `raise ApiError("NOT_FOUND", "会话不存在", 404)`，信封由处理器统一封装。

### 7.3 HTTP 状态码

| 状态 | 用途 |
|---|---|
| 200 | 成功 |
| 201 | 创建成功（注册、建会话、上传文档） |
| 400 | 参数不合法 |
| 401 | 未登录 / token 无效 |
| 403 | 无权限 / 账号禁用 |
| 404 | 资源不存在（**含越权**） |
| 409 | 冲突（重名、会话正在生成） |
| 502 | 工具/上游失败 |
| 503 | 功能关闭、MCP 不可用 |
| 504 | 超时 |
| 500 | 未捕获异常 |

### 7.4 错误码全表（22 个）

| code | HTTP | 含义 |
|---|---|---|
| `INVALID_ARGUMENT` | 400 | 参数不合法 |
| `AUTH_BAD_CREDENTIALS` | 401 | 用户名或密码错误 |
| `AUTH_TOKEN_INVALID` | 401 | token 无效或过期 |
| `AUTH_USERNAME_TAKEN` | 409 | 用户名已存在 |
| `AUTH_WEAK_PASSWORD` | 400 | 密码少于 8 位 |
| `AUTH_DISABLED` | 403 | 账号被禁用 |
| `AUTH_REGISTER_CLOSED` | 403 | 未开放注册 |
| `FORBIDDEN` | 403 | 需要 root 权限 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `CONV_BUSY` | 409 | 该会话正在生成回复 |
| `MSG_EMPTY` | 400 | 消息内容为空 |
| `LLM_FAILED` | 500 | 模型调用失败 |
| `LLM_TIMEOUT` | 504 | 模型超时 |
| `TOOL_NOT_FOUND` | 404 | 工具不存在 |
| `TOOL_FAILED` | 502 | 工具调用失败 |
| `TOOL_UNAVAILABLE` | 503 | 对应 MCP Server 没起来 |
| `RAG_DISABLED` | 503 | 知识库未启用 |
| `RAG_FILE_TYPE` | 400 | 不支持的文件类型 |
| `RAG_FILE_TOO_LARGE` | 400 | 文件太大 |
| `RAG_EMPTY_TEXT` | 400 | 没提取到正文 |
| `RAG_URL_BLOCKED` | 400 | URL 不允许抓取 |
| `INTERNAL_ERROR` | 500 | 未捕获异常 |

新增错误码必须同时更新本文档与前端文档的提示文案表。

### 7.5 权限与越权

| 标记 | 含义 |
|---|---|
| 🔓 | 免登录 |
| 👤 | 需登录 |
| 🔒 | 需登录且只能操作**自己的**资源 |
| 👑 | 仅 `root` |

**越权一律返回 404。** 访问别人的会话/消息返回 `NOT_FOUND` 而不是 `FORBIDDEN`，避免"这个 ID 存在"的信息泄露。

**越权校验必须在 service 层显式做**：

```python
async def get_conversation(db, conv_id: str, user: User) -> Conversation:
    conv = await db.get(Conversation, conv_id)
    if conv is None or conv.user_id != user.id:      # 两个条件缺一不可
        raise ApiError("NOT_FOUND", "会话不存在", 404)
    return conv
```

`root` 不因为角色获得数据豁免——root 走 `/api/v1/auth/me`、`/conversations/*` 时同样只能看自己的会话。跨用户的能力只在 `/api/v1/admin/*` 里，且那些接口**不返回对话内容**。

### 7.6 接口总览（20 个）

| 分组 | 数量 | 接口 |
|---|---|---|
| 认证 | 4 | `POST /auth/register`、`POST /auth/login`、`GET /auth/me`、`PUT /auth/profile` |
| 会话 | 4 | `POST /conversations`、`GET /conversations`、`PATCH /conversations/{id}`、`DELETE /conversations/{id}` |
| 消息 | 2 | `GET /conversations/{id}/messages`、`POST /conversations/{id}/messages` |
| 实时 | 1 | `WS /ws/chat` |
| 工具 | 2 | `GET /tools`、`POST /tools/{name}/invoke` |
| 知识库 | 5 | `POST /rag/documents`、`POST /rag/documents/from-url`、`GET /rag/documents`、`DELETE /rag/documents/{id}`、`GET /rag/search` |
| 用户管理 | 2 | `GET /admin/users`、`PATCH /admin/users/{id}` |

---

## 8. 认证接口

### 8.1 `POST /api/v1/auth/register` 🔓

**作用**：自助注册普通用户（`role=user`）。受 `TPA_ALLOW_REGISTER` 控制。

**请求**

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `username` | str | 是 | 3–32 字符，`^[A-Za-z0-9_.-]+$` |
| `password` | str | 是 | ≥8 位 |

```http
POST /api/v1/auth/register
Content-Type: application/json

{ "username": "alice", "password": "pass1234" }
```

**响应 201**

```json
{
  "ok": true,
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "user": { "id": "u_01", "username": "alice", "role": "user" }
  },
  "error": null
}
```

**错误**：`AUTH_USERNAME_TAKEN`(409)、`AUTH_WEAK_PASSWORD`(400)、`AUTH_REGISTER_CLOSED`(403)、`INVALID_ARGUMENT`(400)

**副作用**：注册成功直接签发 token，前端免二次登录。

### 8.2 `POST /api/v1/auth/login` 🔓

```http
POST /api/v1/auth/login
Content-Type: application/json

{ "username": "alice", "password": "pass1234" }
```

**响应 200**：结构同注册（`token` + `user`）。

**判定顺序（顺序不能乱）**

1. 用户不存在 → `AUTH_BAD_CREDENTIALS`
2. `status=disabled` → `AUTH_DISABLED`
3. 密码不匹配 → `AUTH_BAD_CREDENTIALS`

前两步与第三步行数相当，效果上让攻击者无法区分"用户不存在"和"密码错"。

**JWT payload**（HS256，12 小时）

```json
{
  "sub": "u_01",
  "username": "alice",
  "role": "user",
  "iat": 1742280000,
  "exp": 1742284320,
  "iss": "tpa"
}
```

> Demo 只放必需字段。权限判断**不依赖 token 里的 role**——每次请求都查库拿最新 `role` 和 `status`，这样"禁用立即生效"和"改角色立即生效"都不用等 token 过期。查询开销在 Demo 量级可忽略。

### 8.3 `GET /api/v1/auth/me` 👤

**作用**：前端进入任意页面时调用，判断登录态、拿 `role` 决定是否显示管理菜单。

**响应 200**

```json
{
  "ok": true,
  "data": {
    "id": "u_01",
    "username": "alice",
    "role": "user",
    "status": "active",
    "profile": { "home_city": "上海", "dietary": ["不吃辣"] }
  },
  "error": null
}
```

**错误**：`AUTH_TOKEN_INVALID`(401)、`AUTH_DISABLED`(403)

### 8.4 `PUT /api/v1/auth/profile` 👤

**作用**：整体替换自己的用户画像（6.5）。

**请求**

```json
{
  "home_city": "上海",
  "budget_level": "comfortable",
  "pace": "balanced",
  "interests": ["历史", "博物馆"],
  "dietary": ["不吃辣"],
  "avoid": ["长途大巴"]
}
```

**响应 200**

```json
{ "ok": true, "data": { "profile": { "home_city": "上海", "...": "..." } }, "error": null }
```

**规则**
- 未知键忽略（不报错，方便前端多传）。
- 值类型不对 → `INVALID_ARGUMENT`。
- 整体替换：不传某个键就是"清空该项"。
- 空对象 `{}` 合法，表示清空画像。

---

## 9. 会话与消息接口

### 9.1 数据对象

**`Conversation`**

```json
{
  "id": "c_01",
  "title": "杭州周末两天",
  "message_count": 6,
  "has_itinerary": true,
  "created_at": "2025-03-18T01:20:00Z",
  "updated_at": "2025-03-18T02:05:11Z"
}
```

> `message_count` 与 `has_itinerary` 是**计算字段**（`COUNT` 子查询 / 检查是否存在含 `itinerary` 的消息）。前端列表用它显示"已生成行程"徽标。

**`Message`**

```json
{
  "id": "m_02",
  "seq": 2,
  "role": "assistant",
  "content": "根据预报，杭州周六多云 18–24℃……",
  "status": "completed",
  "itinerary": { "title": "杭州周末 2 日游", "days": [] },
  "citations": [
    { "document_id": "d_01", "title": "杭州西湖景区预约须知",
      "ordinal": 3, "score": 0.8123, "snippet": "自 2025 年 3 月 1 日起……" }
  ],
  "tool_calls": [
    { "name": "weather_forecast", "args": { "city": "杭州", "days": 2 }, "ok": true, "ms": 312 }
  ],
  "created_at": "2025-03-18T02:04:02Z"
}
```

---

### 9.2 `POST /api/v1/conversations` 👤

**作用**：新建空会话。

**请求**（可为空对象）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | str | 否 | 缺省 `新对话`，≤60 |

**响应 201**

```json
{ "ok": true, "data": { "id": "c_01", "title": "新对话",
  "created_at": "2025-03-18T01:20:00Z", "updated_at": "2025-03-18T01:20:00Z" }, "error": null }
```

### 9.3 `GET /api/v1/conversations` 👤

**作用**：列出自己的会话，按 `updated_at` 倒序。

**查询参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `page` | int | 1 | —— |
| `page_size` | int | 20 | 1–100 |

**响应 200**

```json
{
  "ok": true,
  "data": {
    "items": [
      { "id": "c_01", "title": "杭州周末两天", "message_count": 6,
        "has_itinerary": true,
        "created_at": "2025-03-18T01:20:00Z",
        "updated_at": "2025-03-18T02:05:11Z" }
    ],
    "total": 1
  },
  "error": null
}
```

### 9.4 `GET /api/v1/conversations/{id}/messages` 🔒

**作用**：取会话全部消息。**不分页**（Demo 会话不会超 200 条）。

**查询参数**：`limit`（默认 200，上限 500）

**响应 200**

```json
{
  "ok": true,
  "data": {
    "conversation": { "id": "c_01", "title": "杭州周末两天" },
    "items": [ { "id": "m_01", "seq": 1, "role": "user", "...": "..." } ]
  },
  "error": null
}
```

**同时返回 `conversation` 的原因**：前端可能直接用会话 URL 进入，一次请求就能拿到标题，少一次往返。

**排序**：按 `seq` 升序。

**错误**：`NOT_FOUND`(404)

### 9.5 `PATCH /api/v1/conversations/{id}` 🔒

**作用**：改标题。

```json
{ "title": "杭州 3 月周末" }
```

**响应 200**：更新后的 `Conversation`。

**错误**：`NOT_FOUND`(404)、`INVALID_ARGUMENT`(400，标题超 60 或为空)

### 9.6 `DELETE /api/v1/conversations/{id}` 🔒

**作用**：删除会话及其全部消息（级联，不可恢复）。

**响应 200**

```json
{ "ok": true, "data": { "deleted": true }, "error": null }
```

**实现注意**：SQLite 必须开 `PRAGMA foreign_keys = ON`，否则 `ON DELETE CASCADE` 不生效、会留下孤儿消息。更保险的写法是在 service 里显式两步删除（先删消息再删会话），不依赖数据库行为。

**错误**：`NOT_FOUND`(404)

---

## 10. 非流式发消息

### 10.1 `POST /api/v1/conversations/{id}/messages` 🔒

**作用**：发一条用户消息，**同步等 LLM 跑完**后返回完整结果。

**为什么保留**：主通道是 WebSocket（第 11 章），但这个接口让 `curl` 或脚本就能测通整条链路，不用写 WS 客户端。排障时非常好用。

**请求**

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `content` | str | 是 | 1–8000 字符，去空白后非空 |

```http
POST /api/v1/conversations/c_01/messages
Authorization: Bearer <token>
Content-Type: application/json

{ "content": "这周末去杭州两天，预算 1500" }
```

**响应 200**（可能等 10–60 秒）

```json
{
  "ok": true,
  "data": {
    "user_message": {
      "id": "m_05", "seq": 5, "role": "user",
      "content": "这周末去杭州两天，预算 1500", "status": "completed"
    },
    "assistant_message": {
      "id": "m_06", "seq": 6, "role": "assistant",
      "content": "根据周六、周日天气……",
      "status": "completed",
      "itinerary": { "title": "杭州周末 2 日游", "days": [] },
      "citations": [],
      "tool_calls": [
        { "name": "weather_forecast", "args": { "city": "杭州", "days": 2 }, "ok": true, "ms": 312 }
      ]
    }
  },
  "error": null
}
```

**错误**：`NOT_FOUND`(404)、`CONV_BUSY`(409)、`MSG_EMPTY`(400)、`LLM_TIMEOUT`(504)、`LLM_FAILED`(500)

**内部流程**（与 WS 完全一致，只是事件不外发）

```
1. 校验会话归属
2. 获取会话锁，拿不到 → CONV_BUSY
3. 落库 user 消息（seq = max+1）
4. 落库 assistant 占位（seq = max+2, status=pending）
5. 装配上下文 → 跑 agent.run()，把所有事件丢进列表
6. 落库 assistant 最终内容（status=completed）
7. 释放锁，返回两个消息对象
8. 异步：生成会话标题（失败不影响响应）
```

**超时设置**：`uvicorn` 默认无请求超时，但前端要有 90 秒上限。若 LLM 超过 90 秒仍未返回，前端应放弃等待并提示"生成较慢，请刷新查看"——消息仍在服务端继续生成并落库。

---

## 11. WebSocket 对话

### 11.1 端点与握手

```
WS /api/v1/ws/chat
```

| 项 | 规定 |
|---|---|
| 帧类型 | 只接受 `text` 帧，载荷为 UTF-8 JSON |
| 认证 | **不在 URL 带 token**，连上后发 `auth` 帧 |
| 认证窗口 | 10 秒内未完成认证则关闭（`4001`） |
| 心跳 | 服务端不做。前端 30 秒无帧自行重连 |
| 帧大小 | ≤64 KB |

**为什么 token 不放 URL**：URL 会被写进 Nginx 访问日志、浏览器历史、Referer。放 WS 载荷里就避开了。

### 11.2 帧格式

统一结构：`{ "type": str, "data": object|null }`。不带 `ts`、不带 `seq`——Demo 不需要。

**上行 3 种**

```json
{ "type": "auth", "data": { "token": "eyJ..." } }

{ "type": "message", "data": {
    "conversation_id": "c_01",
    "content": "这周末去杭州两天"
} }

{ "type": "cancel", "data": { "conversation_id": "c_01" } }
```

**下行 5 种**

#### `auth_ok`

```json
{ "type": "auth_ok", "data": { "user_id": "u_01", "role": "user" } }
```

#### `tool`

工具调用的开始与结束**共用同一个 type**，靠 `phase` 区分。

```json
{ "type": "tool", "data": {
    "phase": "start",
    "name": "weather_forecast",
    "args": { "city": "杭州", "days": 2 }
} }
```

```json
{ "type": "tool", "data": {
    "phase": "end",
    "name": "weather_forecast",
    "ok": true,
    "ms": 312,
    "summary": "3/22 多云 18–24℃；3/23 阵雨 16–21℃"
} }
```

- `args` 与 `summary` 各截断到 2 KB。
- `summary` 由后端从工具结果里提取**人话摘要**（不是原始 JSON）：天气取每天现象+温度；POI 取命中数；路线取距离+耗时。

#### `token`

```json
{ "type": "token", "data": { "delta": "根据预报，" } }
```

**`delta` 是增量**，前端必须 append。保证同一轮所有 `delta` 顺序拼接后与 `done.message.content` 一致。

#### `itinerary`

```json
{ "type": "itinerary", "data": { "title": "杭州周末 2 日游", "days": [] } }
```

最多发一次。Schema 见 16.4。

#### `done`

```json
{ "type": "done", "data": {
    "status": "completed",
    "message": {
      "id": "m_06",
      "seq": 6,
      "content": "完整文本…",
      "citations": [ ]
    },
    "title": "杭州周末两天"
} }
```

`status` 取值：`completed` / `failed` / `cancelled`。

`sent` 语义：**唯一终态信号**。前端收到它就停止 loading，并用 `message.content` 覆盖累积文本（防丢字）。`title` 是可能更新后的会话标题。

#### `error`

```json
{ "type": "error", "data": { "code": "CONV_BUSY", "message": "该会话正在生成回复" } }
```

发完 `error` 后**连接保持**（可继续发 `message`）。只有认证失败才断连。

### 11.3 时序

```
客户端                        服务端
  │ ── auth{token} ───────────►│
  │ ◄──────────── auth_ok ─────│
  │ ── message{...} ──────────►│  校验、拿锁、落库两条消息
  │ ◄──────────── tool{start} ─│
  │ ◄──────────── tool{end} ───│
  │ ◄──────────── tool{start} ─│
  │ ◄──────────── tool{end} ───│
  │ ◄──────────── token ───────│
  │ ◄──────────── token ───────│
  │ ◄──────────── itinerary ───│
  │ ◄──────────── done ────────│
```

**取消场景**

```
  │ ── cancel ────────────────►│
  │ ◄──────────── done{cancelled} │  已生成内容已落库
```

### 11.4 服务端实现要点

| 要点 | 做法 |
|---|---|
| 生成是后台任务 | `asyncio.create_task(run_round(...))`，WS 只消费它的事件队列。断连不取消任务 |
| 事件队列 | `asyncio.Queue`，`run_round` 往里 `put` 事件，WS 协程 `get` 后 `send_json` |
| 取消 | `task.cancel()` + `except asyncio.CancelledError` 里把消息标 `cancelled` |
| 会话锁 | `locks.setdefault(conv_id, asyncio.Lock())`，`locked()` 为真时直接回 `CONV_BUSY` |
| 发送失败 | 连接已断 → 捕获 `WebSocketDisconnect`，停止消费队列，**但后台任务继续跑完并落库** |
| 认证失败 | `await ws.close(code=4001)` |

**最容易写错的一点**：不要把"生成"和"发送"写在同一个协程里。分开之后"用户关掉页面，回复照样生成完"这个体验才成立。

### 11.5 关闭码

| code | 含义 | 前端处理 |
|---|---|---|
| `1000` | 正常关闭 | 不重连 |
| `4001` | 认证失败 | 不重连，跳登录页 |
| `4002` | 帧格式错 | 不重连，属客户端 bug |
| `1011` | 服务端异常 | 重连一次 |

---

## 12. 工具接口

### 12.1 `GET /api/v1/tools` 👤

**作用**：列出当前可用工具与 MCP Server 状态。前端"关于/调试"页和排障用。

**响应 200**

```json
{
  "ok": true,
  "data": {
    "servers": [
      { "name": "weather", "status": "connected", "tool_count": 2 },
      { "name": "place",   "status": "connected", "tool_count": 3 }
    ],
    "tools": [
      { "name": "weather_now",      "server": "weather", "description": "查询城市实时天气" },
      { "name": "weather_forecast", "server": "weather", "description": "查询未来 1–4 天天气预报" },
      { "name": "place_search",     "server": "place",   "description": "按关键字搜索地点" },
      { "name": "geo_geocode",      "server": "place",   "description": "地址转坐标" },
      { "name": "route_plan",       "server": "place",   "description": "计算两点距离与耗时" },
      { "name": "search_knowledge_base", "server": null, "description": "检索内置知识库" }
    ],
    "degraded": false
  },
  "error": null
}
```

`servers[].status`：`connected` / `disconnected` / `failed`。
`degraded`：`true` 表示有 Server 不可用，Agent 能力受限。

### 12.2 `POST /api/v1/tools/{name}/invoke` 👤

**作用**：手动调任意工具，直接看到真实 JSON 结构。**排障和演示都靠它**。

**请求**

```json
{ "args": { "city": "杭州", "days": 2 } }
```

**响应 200**

```json
{
  "ok": true,
  "data": {
    "tool": "weather_forecast",
    "duration_ms": 288,
    "result": {
      "ok": true,
      "tool": "weather_forecast",
      "provider": "amap",
      "latency_ms": 271,
      "data": {
        "city": "杭州市",
        "adcode": "330100",
        "forecast": [ { "date": "2025-03-22", "day_weather": "多云" } ]
      },
      "error": null
    }
  },
  "error": null
}
```

**两层信封都要保留**：外层 `data` 是接口信封，`data.result` 是工具自己的信封（第 15 章）。这样排障时能区分"接口挂了"和"工具挂了"。

**实现**：`services/mcp_manager.invoke(name, args)`，内部从已发现的工具表里查找并调用。工具不存在 → `TOOL_NOT_FOUND`；Server 不可用 → `TOOL_UNAVAILABLE`。

**安全**：`/invoke` 不写消息、不消耗 LLM 配额，但**必须要求登录**（否则内网任何人可打爆高德 Key）。Demo 里给所有登录用户开放即可，生产要收到 root。

---

## 13. 知识库接口

基础路径 `/api/v1/rag`。**全部 👑 仅 root**（普通用户只能通过 Agent 间接使用）。

> 设计取舍：知识库是**公共资产**，只由 root 维护，避免普通用户上传投毒。若 `TPA_RAG_ENABLED=false`，本组全部返回 `503 RAG_DISABLED`。

### 13.1 `POST /api/v1/rag/documents` 👑

**作用**：上传文件，**同步**解析、分块、嵌入、入库。等 5–30 秒直接返回结果（Demo 不做异步任务和进度轮询）。

**请求（multipart/form-data）**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | binary | 是 | `.pdf`/`.docx`/`.md`/`.txt`/`.csv`，≤20 MB |
| `title` | str | 否 | 缺省取文件名（去扩展名） |

```http
POST /api/v1/rag/documents
Authorization: Bearer <root_token>
Content-Type: multipart/form-data; boundary=----X

------X
Content-Disposition: form-data; name="file"; filename="西湖预约须知.pdf"
Content-Type: application/pdf
<binary>
------X
Content-Disposition: form-data; name="title"
杭州西湖景区 2025 年预约须知
------X--
```

**响应 201（成功）**

```json
{
  "ok": true,
  "data": {
    "id": "d_01",
    "title": "杭州西湖景区 2025 年预约须知",
    "source_type": "file",
    "status": "ready",
    "chunk_count": 24,
    "chunk_preview": [
      "第一章 总则：自 2025 年 3 月 1 日起，西湖景区实行分时段预约……",
      "预约渠道：通过「西湖景区」官方公众号提前 1–7 天预约……"
    ]
  },
  "error": null
}
```

`chunk_preview` 返回**前 3 块**的前 100 字，让 root 一眼看出切得对不对——这是调 RAG 效果最快的手段。

**响应 201（入库失败）**

```json
{
  "ok": true,
  "data": {
    "id": "d_02",
    "title": "扫描件.pdf",
    "source_type": "file",
    "status": "failed",
    "chunk_count": 0,
    "error": "未能提取到文本，可能是扫描版 PDF，请先 OCR"
  },
  "error": null
}
```

> **失败也返回 201**，靠 `status` 区分。这样前端能在列表里看到失败记录和原因，比直接抛错更利于演示和排查。

**错误**（这些是"请求根本不该进来"的情况）

| 场景 | 错误码 |
|---|---|
| 扩展名不在白名单 | `RAG_FILE_TYPE`(400) |
| 超过 20 MB | `RAG_FILE_TOO_LARGE`(400) |
| RAG 未启用 | `RAG_DISABLED`(503) |
| 非 root | `FORBIDDEN`(403) |

**校验清单（按顺序）**

1. 扩展名在 `{pdf, docx, md, txt, csv}` 内
2. 大小 ≤ 20 MB（**流式读取时边读边计数**，不要先全读进内存）
3. 文件头魔数匹配（`%PDF-` / `PK\x03\x04` / 文本类可 UTF-8 解码）
4. 文件名剥离路径、过滤 `..` 和 `/`
5. 落盘 `data/uploads/{document_id}/{safe_name}`

### 13.2 `POST /api/v1/rag/documents/from-url` 👑

**作用**：抓网页正文入库，用于跟踪"景区最新公告""交通新规"这类会变的信息。

**请求**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `url` | str | 是 | `http`/`https`，≤2048 |
| `title` | str | 否 | 缺省取网页 `<title>`，再缺省取 URL |

```json
{ "url": "https://example.gov.cn/notice/2025-03-01.html" }
```

**响应 201**：结构同 13.1。

**SSRF 防护（Demo 也必须有，就几行代码）**

```python
# 1. 协议白名单
if urlparse(url).scheme not in ("http", "https"):
    raise ApiError("RAG_URL_BLOCKED", "只允许 http/https", 400)

# 2. 解析所有 IP，命中保留网段就拒
BLOCKED = [ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    "169.254.0.0/16", "0.0.0.0/8", "::1/128", "fc00::/7", "fe80::/10",
)]
for ip in {i[4][0] for i in socket.getaddrinfo(host, None)}:
    if any(ipaddress.ip_address(ip) in n for n in BLOCKED):
        raise ApiError("RAG_URL_BLOCKED", "该地址不允许抓取", 400)

# 3. 不跟随重定向（防止"公网 302 到内网"绕过）
resp = await client.get(url, follow_redirects=False, timeout=15)
```

再加两条：响应体上限 5 MB（边读边计数）、超时 15 秒。

### 13.3 `GET /api/v1/rag/documents` 👑

**响应 200**

```json
{
  "ok": true,
  "data": {
    "items": [
      { "id": "d_01", "title": "杭州西湖景区 2025 年预约须知",
        "source_type": "file", "filename": "西湖预约须知.pdf",
        "status": "ready", "chunk_count": 24,
        "created_at": "2025-03-18T03:00:00Z" }
    ]
  },
  "error": null
}
```

按 `created_at` 倒序，不分页（Demo 文档数不会多）。

### 13.4 `DELETE /api/v1/rag/documents/{id}` 👑

**作用**：删除文档、其 Chroma 向量、磁盘文件。

**执行顺序（保证可重入）**

1. 按 `document_id` 删 Chroma 向量：`collection.delete(where={"document_id": {"$eq": id}})`
2. 删 `rag_documents` 行
3. 删 `data/uploads/{id}/` 目录

中途失败只记 WARNING，逻辑上文档已删（检索不会再命中）。

**响应 200**：`{ "ok": true, "data": { "deleted": true } }`

**错误**：`NOT_FOUND`(404)

### 13.5 `GET /api/v1/rag/search` 👑

**作用**：**检索调试接口**——演示 RAG 效果最有用的一个。能区分"检索不到"和"检索到了但模型没用"。

**查询参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `q` | str | 是 | 1–200 字符 |
| `top_k` | int | 否 | 1–20，默认取 `TPA_RAG_TOP_K` |

```http
GET /api/v1/rag/search?q=西湖景区预约规则&top_k=5
Authorization: Bearer <root_token>
```

**响应 200**

```json
{
  "ok": true,
  "data": {
    "query": "西湖景区预约规则",
    "elapsed_ms": 46,
    "hits": [
      { "document_id": "d_01",
        "title": "杭州西湖景区 2025 年预约须知",
        "ordinal": 3,
        "score": 0.8123,
        "snippet": "自 2025 年 3 月 1 日起，西湖景区实行分时段预约……" }
    ]
  },
  "error": null
}
```

**错误**：`INVALID_ARGUMENT`(400，q 为空)、`RAG_DISABLED`(503)

---

## 14. 用户管理接口

基础路径 `/api/v1/admin`，**全部 👑**。

### 14.1 `GET /api/v1/admin/users`

**响应 200**

```json
{
  "ok": true,
  "data": {
    "items": [
      { "id": "u_01", "username": "alice", "role": "user", "status": "active",
        "conversation_count": 12, "created_at": "2025-03-01T08:00:00Z" },
      { "id": "u_00", "username": "root", "role": "root", "status": "active",
        "conversation_count": 3, "created_at": "2025-03-01T07:00:00Z" }
    ],
    "total": 2
  },
  "error": null
}
```

> 只返回会话**数量**，绝不返回任何对话内容。这是隐私边界。

### 14.2 `PATCH /api/v1/admin/users/{id}`

**作用**：改角色或启用/禁用。

```json
{ "role": "root" }
```
```json
{ "status": "disabled" }
```

**响应 200**：更新后的用户对象（`id`/`username`/`role`/`status`）。

**三条规则（顺序不能省）**

1. 不能改自己 → `FORBIDDEN`(403)。防止管理员把自己降级成 user 后再也进不来。
2. 必须留至少一个 `role=root AND status=active` 的账号 → `FORBIDDEN`(403)。防止把系统锁死。
3. 禁用后**立即生效**：因为每次请求都查库校验 `status`，不依赖 token 内容。

**错误**：`NOT_FOUND`(404)、`FORBIDDEN`(403)、`INVALID_ARGUMENT`(400)

---

## 15. MCP 工具契约

本章是**工具层与 Agent 层的唯一契约**。改工具必须同步改这里。

### 15.1 基础约定

| 项 | 规定 |
|---|---|
| 协议 | MCP，JSON-RPC 2.0 over **stdio** |
| SDK | 官方 `mcp`，服务端用 `FastMCP` |
| 启动 | 后端 `lifespan` 里 `subprocess` 拉起两个子进程 |
| Server 名 | `weather`、`place` |
| 工具数 | **5 个**（weather 2 + place 3） |
| 工具命名 | `snake_case`，全局唯一 |
| **日志** | **一律写 stderr**。stdout 是 JSON-RPC 通道，写日志会直接搞坏通信——这是最常见的集成事故 |
| 启动超时 | 20 秒 |
| 调用超时 | 15 秒 |
| 重试 | 只对网络类错误额外重试 1 次 |
| 缓存 / 熔断 | 不做 |
| 进程重启 | 崩溃后重启，最多 3 次；超了标记 `failed`，Agent 降级 |

### 15.2 统一返回信封（核心）

**所有工具必须返回同一个结构**，不许返回裸数组或裸对象。

**成功**

```json
{
  "ok": true,
  "tool": "weather_now",
  "provider": "amap",
  "latency_ms": 271,
  "data": { },
  "error": null
}
```

**失败**

```json
{
  "ok": false,
  "tool": "weather_now",
  "provider": "amap",
  "latency_ms": 8003,
  "data": null,
  "error": { "code": "TIMEOUT", "message": "高德天气接口超时", "retryable": true }
}
```

| 字段 | 类型 | 必有 | 说明 |
|---|---|---|---|
| `ok` | bool | 是 | **唯一**成功标志。不要用 `data` 是否为空来判断 |
| `tool` | str | 是 | 工具名回显 |
| `provider` | str | 是 | 数据源，现在是 `amap`，换源会变 |
| `latency_ms` | int | 是 | 工具内部耗时 |
| `data` | obj \| null | 是 | 成功时的数据，失败时恒为 `null` |
| `error` | obj \| null | 是 | 失败时 `{code, message, retryable}`，成功时恒为 `null` |

**MCP 双写**（保证新旧客户端都能用，也便于 schema 断言）

```python
def envelope_ok(tool: str, data: dict, latency_ms: int) -> dict:
    return {"ok": True, "tool": tool, "provider": "amap",
            "latency_ms": latency_ms, "data": data, "error": None}

def envelope_err(tool: str, code: str, message: str,
                 retryable: bool, latency_ms: int) -> dict:
    return {"ok": False, "tool": tool, "provider": "amap",
            "latency_ms": latency_ms, "data": None,
            "error": {"code": code, "message": message, "retryable": retryable}}

def as_mcp_result(env: dict) -> dict:
    return {
        "structuredContent": env,
        "content": [{"type": "text", "text": json.dumps(env, ensure_ascii=False)}],
        "isError": not env["ok"],
    }
```

两份内容必须完全一致——测试里直接断言 `json.loads(content[0]["text"]) == structuredContent`。

### 15.3 工具错误码

工具层**独立命名空间**（与第 7.4 节的 REST 错误码不是一套，由 `mcp_manager` 做映射）。

| code | retryable | 含义 | 上层怎么处理 |
|---|---|---|---|
| `INVALID_ARGUMENT` | false | 参数不对 | 错误文本回给模型，让它改参数 |
| `NOT_FOUND` | false | 查不到（城市不存在、无匹配） | 回给模型，提示换关键词 |
| `UPSTREAM_ERROR` | true | 高德异常 | 重试 1 次，仍失败返回 |
| `UPSTREAM_RATE_LIMITED` | true | 高德限流 | 重试 1 次 |
| `UPSTREAM_AUTH_FAILED` | false | Key 无效/无权限 | **不重试**，打 ERROR 日志 |
| `TIMEOUT` | true | 超时 | 重试 1 次 |
| `NOT_IMPLEMENTED` | false | 能力未实现 | 直接返回 |

**REST 侧映射**（`/tools/{name}/invoke` 之外的调用路径用）

| 工具错误 | REST 错误码 |
|---|---|
| `INVALID_ARGUMENT` | `INVALID_ARGUMENT` |
| `NOT_FOUND` | `TOOL_FAILED`（带原文） |
| `UPSTREAM_*` / `TIMEOUT` | `TOOL_FAILED` |
| Server 不可用 | `TOOL_UNAVAILABLE` |

### 15.4 高德 `infocode` 映射

`status=1` 且 `info=OK` 才算成功；`count=0` 视为 `NOT_FOUND`。

| infocode | 含义 | 映射到 |
|---|---|---|
| `10000` | 成功 | —— |
| `10001` | Key 不正确/过期 | `UPSTREAM_AUTH_FAILED` |
| `10005` | IP 白名单错 | `UPSTREAM_AUTH_FAILED` |
| `10009` | 权限不足 | `UPSTREAM_AUTH_FAILED` |
| `10003` | 日访问量超限 | `UPSTREAM_RATE_LIMITED` |
| `10004` | 访问过于频繁 | `UPSTREAM_RATE_LIMITED` |
| `10044` | 账号日调用量超限 | `UPSTREAM_RATE_LIMITED` |
| `20000`–`20002` | 参数错误 | `INVALID_ARGUMENT` |
| `20800`–`20802` | 路径规划参数错/无结果 | `INVALID_ARGUMENT` / `NOT_FOUND` |
| `30000` | 引擎超时 | `TIMEOUT` |
| 其他 | —— | `UPSTREAM_ERROR` |

### 15.5 通用字段约定

| 项 | 规定 |
|---|---|
| 坐标 | GCJ-02，`"经度,纬度"`，6 位小数 |
| 城市 | 参数名 `city`，接受中文名或 adcode，内部统一下转 adcode |
| 温度 | 整数℃，字段 `*_temp_c` |
| 日期 | `YYYY-MM-DD`，时区 `Asia/Shanghai` |
| 距离/时长 | 整数，`*_m` / `*_s` |
| 金额 | 整数分，`*_cent` |
| 空值 | 高德没返回的字段显式给 `null`，**不省略键** |
| 截断 | `steps` 最多 50 条；`pois` 最多 25 条 |

### 15.6 Server `weather`（2 个工具）

启动：`python -m mcp_servers.weather`
上游：`GET https://restapi.amap.com/v3/weather/weatherInfo`

#### `weather_now`

**描述**（也用于 `tools/list`，模型会读）：查询中国境内城市当前实时天气，返回天气现象、温度、风向风力、湿度。

**输入 Schema**

```json
{
  "type": "object",
  "properties": {
    "city": { "type": "string", "minLength": 1, "maxLength": 32,
              "description": "城市中文名（如 杭州）或 6 位 adcode（如 330100）" }
  },
  "required": ["city"],
  "additionalProperties": false
}
```

**成功输出**

```json
{
  "ok": true, "tool": "weather_now", "provider": "amap", "latency_ms": 271,
  "data": {
    "city": "杭州市",
    "adcode": "330100",
    "province": "浙江省",
    "weather": "多云",
    "temperature_c": 22,
    "wind_direction": "东南风",
    "wind_power": "1-3",
    "humidity": 62,
    "report_time": "2025-03-18T14:00:00+08:00"
  },
  "error": null
}
```

| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| `city` | str | 否 | 城市全名 |
| `adcode` | str | 否 | 解析后的 adcode |
| `province` | str | 否 | 省份 |
| `weather` | str | 否 | 天气现象 |
| `temperature_c` | int | 否 | ℃ |
| `wind_direction` | str | 是 | 风向 |
| `wind_power` | str | 是 | 风力等级 |
| `humidity` | int | 是 | % |
| `report_time` | str | 否 | 发布时间（+08:00） |

**错误**：`INVALID_ARGUMENT`、`NOT_FOUND`（城市解析不出 adcode）、`UPSTREAM_*`、`TIMEOUT`

#### `weather_forecast`

**描述**：查询城市未来 1–4 天天气预报，含每日天气、温度区间、出行建议与降水风险。

**输入 Schema**

```json
{
  "type": "object",
  "properties": {
    "city": { "type": "string", "minLength": 1, "maxLength": 32 },
    "days": { "type": "integer", "minimum": 1, "maximum": 4, "default": 3 }
  },
  "required": ["city"],
  "additionalProperties": false
}
```

**成功输出**

```json
{
  "ok": true, "tool": "weather_forecast", "provider": "amap", "latency_ms": 305,
  "data": {
    "city": "杭州市",
    "adcode": "330100",
    "report_time": "2025-03-18T11:00:00+08:00",
    "forecast": [
      { "date": "2025-03-22", "weekday": "星期六",
        "day_weather": "多云", "night_weather": "多云",
        "day_temp_c": 24, "night_temp_c": 18,
        "day_wind": "东南风", "day_power": "1-3",
        "advice": "适合户外活动", "rain_risk": "low" },
      { "date": "2025-03-23", "weekday": "星期日",
        "day_weather": "阵雨", "night_weather": "小雨",
        "day_temp_c": 21, "night_temp_c": 16,
        "day_wind": "北风", "day_power": "3-4",
        "advice": "建议安排室内活动并携带雨具", "rain_risk": "high" }
    ]
  },
  "error": null
}
```

**`advice` / `rain_risk` 派生规则**（`server.py` 里的纯函数 `_derive_advice()`，可单测）

| 天气现象含 | rain_risk | advice |
|---|---|---|
| 暴雨 / 大暴雨 / 雷阵雨 | `high` | 建议改为室内活动，注意积水与交通管制 |
| 阵雨 / 中雨 / 大雨 / 雪 / 雨夹雪 | `high` | 建议安排室内活动并携带雨具 |
| 小雨 / 毛毛雨 | `medium` | 建议携带雨具，户外安排留弹性 |
| 雾 / 霾 / 沙尘 | `medium` | 减少长时间户外活动 |
| 高温（`day_temp_c >= 35`） | `low` | 避开正午户外，注意补水防晒 |
| 晴 / 多云 / 阴（兜底） | `low` | 适合户外活动 |

> 让服务器算好"要不要带伞"，比让模型自己推更准，也省 token。

### 15.7 Server `place`（3 个工具）

启动：`python -m mcp_servers.place`

#### `place_search`

**描述**：按关键字搜索景点、餐厅、酒店等地点，返回名称、坐标、地址、评分。

**输入 Schema**

```json
{
  "type": "object",
  "properties": {
    "keywords":  { "type": "string", "minLength": 1, "maxLength": 50 },
    "city":      { "type": "string", "maxLength": 32 },
    "page_size": { "type": "integer", "minimum": 1, "maximum": 25, "default": 10 }
  },
  "required": ["keywords"],
  "additionalProperties": false
}
```

**成功输出**

```json
{
  "ok": true, "tool": "place_search", "provider": "amap", "latency_ms": 402,
  "data": {
    "total": 128,
    "pois": [
      { "id": "B023B0A63E",
        "name": "西湖风景名胜区",
        "type": "风景名胜;公园广场;公园",
        "address": "龙井路1号",
        "location": "120.153576,30.287459",
        "city": "杭州市",
        "district": "西湖区",
        "rating": "4.7",
        "cost_cent": null }
    ]
  },
  "error": null
}
```

| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| `total` | int | 否 | 匹配总数 |
| `pois[].id` | str | 否 | 高德 POI ID |
| `pois[].name` | str | 否 | 名称 |
| `pois[].type` | str | 否 | 类型路径（分号分隔） |
| `pois[].address` | str | 是 | 地址（POI 可能无门牌） |
| `pois[].location` | str | 否 | 坐标 |
| `pois[].city` / `district` | str | 是 | 行政区 |
| `pois[].rating` | str | 是 | 评分，**高德经常不返回** |
| `pois[].cost_cent` | int | 是 | 人均（分），**经常不返回** |

> ⚠️ `rating`/`cost_cent` 缺失是常态。提示词里必须明确"缺失时说未获取，不要编造"。

#### `geo_geocode`

**描述**：把结构化地址转成经纬度坐标，用于计算路线。

**输入 Schema**

```json
{
  "type": "object",
  "properties": {
    "address": { "type": "string", "minLength": 1, "maxLength": 100 },
    "city":    { "type": "string", "maxLength": 32 }
  },
  "required": ["address"],
  "additionalProperties": false
}
```

**成功输出**

```json
{
  "ok": true, "tool": "geo_geocode", "provider": "amap", "latency_ms": 180,
  "data": {
    "formatted_address": "浙江省杭州市西湖区北山街",
    "location": "120.141872,30.259636",
    "adcode": "330106",
    "city": "杭州市",
    "district": "西湖区",
    "level": "门牌号"
  },
  "error": null
}
```

**`level` 的意义**：匹配精度。取值可能是 `省`/`市`/`区县`/`乡镇`/`兴趣点`/`门牌号`/`道路` 等。若粗于 `区县`，说明地址不够具体，Agent 应据此向用户确认。

#### `route_plan`

**描述**：计算两点之间的距离、耗时与分段路线，用于判断行程是否排得下。

**输入 Schema**

```json
{
  "type": "object",
  "properties": {
    "origin":      { "type": "string", "description": "起点 经度,纬度" },
    "destination": { "type": "string", "description": "终点 经度,纬度" },
    "mode": { "type": "string", "enum": ["driving", "walking", "transit"], "default": "driving" }
  },
  "required": ["origin", "destination", "mode"],
  "additionalProperties": false
}
```

**成功输出**

```json
{
  "ok": true, "tool": "route_plan", "provider": "amap", "latency_ms": 620,
  "data": {
    "mode": "driving",
    "distance_m": 4820,
    "duration_s": 1140,
    "taxi_cost_cent": 1800,
    "steps": [
      { "instruction": "沿北山街向西行驶 800 米", "distance_m": 800, "duration_s": 180 }
    ]
  },
  "error": null
}
```

**超长距离保护**：`mode=walking` 且 `distance_m > 300000` 时直接返回 `INVALID_ARGUMENT`（"该距离不适合步行"），不打上游。

### 15.8 后端原生工具（不走 MCP）

| 工具 | 输入 | 输出 |
|---|---|---|
| `search_knowledge_base` | `{ "query": string }` | `{ "ok": bool, "hits": [{document_id, title, ordinal, score, snippet}] }` |

**为什么不做成 MCP**：它要直接读 Chroma。放独立进程反而要跨进程传向量数据，得不偿失。

**注意**：它不是 MCP 工具，输出**不套** `tool/provider/latency_ms` 信封，只有 `ok` + `hits`。差异在此显式记录。

### 15.9 高德响应的三个坑（实现必看）

| 坑 | 表现 | 统一处理 |
|---|---|---|
| **空数组代替空值** | `"tel": []`、`"cityname": []`、`"level": []` | 映射层统一 `[]` → `None`；字符串 `"[]"` 同样处理 |
| **数字是字符串** | `"distance": "4820"`、`"duration": "1140"` | 统一 `int(float(x))`，转换失败给 `None` 并记 WARNING |
| **成功但 count=0** | `status=1, info=OK, count=0` | 判定为 `NOT_FOUND`，不是"成功空结果" |

### 15.10 字段映射速查

**天气**（`/v3/weather/weatherInfo`）

| 上游 | 我们的 |
|---|---|
| `lives[0].city` | `data.city` |
| `lives[0].adcode` | `data.adcode` |
| `lives[0].weather` | `data.weather` |
| `lives[0].temperature` | `data.temperature_c`（int） |
| `lives[0].winddirection` / `windpower` | `data.wind_direction` / `wind_power` |
| `lives[0].humidity` | `data.humidity`（int） |
| `lives[0].reporttime` | `data.report_time`（补 `+08:00`） |
| `forecasts[0].casts[]` | `data.forecast[]` |
| `casts[].dayweather` / `nightweather` | `.day_weather` / `.night_weather` |
| `casts[].daytemp` / `nighttemp` | `.day_temp_c` / `.night_temp_c`（int） |
| `casts[].daywind` / `daypower` | `.day_wind` / `.day_power` |
| —— | `.weekday`（**自己按 date 算**） |
| —— | `.advice` / `.rain_risk`（**派生**，见 15.6） |

**POI**（`/v3/place/text`）

| 上游 | 我们的 |
|---|---|
| `count` | `data.total`（int） |
| `pois[].id` / `name` / `type` | `.id` / `.name` / `.type` |
| `pois[].address` | `.address`（`[]` → null） |
| `pois[].location` | `.location` |
| `pois[].cityname` / `adname` | `.city` / `.district` |
| `pois[].biz_ext.rating` | `.rating`（`[]` → null） |
| `pois[].biz_ext.cost` | `.cost_cent`（元 × 100 取整） |

> 请求参数加 `extensions=all` 才有 `biz_ext`；基础查询用 `base` 更快，但拿不到评分。

**地理编码**（`/v3/geocode/geo`）

| 上游 | 我们的 |
|---|---|
| `geocodes[0].formatted_address` | `data.formatted_address` |
| `geocodes[0].location` | `data.location` |
| `geocodes[0].adcode` / `citycode` | `data.adcode` / `citycode` |
| `geocodes[0].city` / `district` | `data.city` / `district` |
| `geocodes[0].level` | `data.level`（`[]` → null） |

**路径规划**（`/v3/direction/{driving|walking|transit/integrated}`）

| 上游 | 我们的 |
|---|---|
| `route.paths[0].distance` | `data.distance_m`（int） |
| `route.paths[0].duration` | `data.duration_s`（int） |
| `route.paths[0].steps[]` | `data.steps[]`（最多 50 条） |
| `route.taxi_cost` | `data.taxi_cost_cent`（元 × 100，可能 `[]`） |
| `steps[].instruction` / `road` | `.instruction` / `.road`（`[]` → null） |
| `steps[].distance` / `duration` | `.distance_m` / `.duration_s` |

> `transit` 模式结构差异最大（`route.transits[].segments[].bus.buslines[]`），需要单独写 `_map_transit()`。Demo 阶段可以先只支持 `driving`/`walking`，`transit` 直接返回 `NOT_IMPLEMENTED`。

---

## 16. Agent 设计

### 16.1 运行时结构

```
chat_service
   │
   ├─ 1. 取历史消息（最近 20 条）
   ├─ 2. 取用户 profile → 渲染成一句话
   ├─ 3. 拼系统提示词（6 块）
   ├─ 4. 挂工具（MCP 5 个 + RAG 1 个，按可用性挂）
   ├─ 5. 跑 LangGraph ReAct 图，流式拿事件
   └─ 6. yield 事件 → WS 层推送 / chat_service 落库
```

**关键设计：`agent.run()` 是一个纯异步生成器，只 yield 事件，不碰 WebSocket、不写数据库。**

事件类型：

| 事件 | 载荷 | 消费方 |
|---|---|---|
| `tool_start` | `{name, args}` | WS 推 `tool{phase:start}`；落库累积到 `tool_calls` |
| `tool_end` | `{name, ok, ms, summary}` | WS 推 `tool{phase:end}` |
| `token` | `{delta}` | WS 推 `token`；同时累积到内存缓冲 |
| `itinerary` | `{...行程对象...}` | WS 推 `itinerary` |
| `done` | `{content, citations, status}` | WS 推 `done`；`chat_service` 落库 |

这样做的收益：非流式接口（第 10 章）只需把事件聚合成两个消息对象；"断连后继续生成"也变成免费能力。

### 16.2 工具挂载与降级

```
工具集 = 可用的 MCP 工具（weather 2 + place 3）
       + search_knowledge_base（若 TPA_RAG_ENABLED）
```

**可用性判定**：`mcp_manager` 启动时对每个 Server 做 `initialize` + `tools/list`。成功的才算可用。

| 场景 | 处理 |
|---|---|
| `weather` Server 没起来 | 不挂天气工具；提示词追加"当前无法获取实时天气，不要编造天气数据" |
| `place` Server 没起来 | 不挂地点工具；提示词追加"当前无法查询地点，只能基于用户提供的信息规划" |
| 两个都没起来 | 仍可对话（纯 LLM + RAG），回复开头说明能力受限 |
| 单个工具调用失败 | **把失败结果作为结构化结果返回给模型**（`ok=false` + 错误说明），不抛异常 |

**最后一条是健壮性的核心。**

```python
async def safe_call(tool, args) -> dict:
    try:
        return await asyncio.wait_for(tool.ainvoke(args), timeout=15)
    except asyncio.TimeoutError:
        return {"ok": False, "error": {"code": "TIMEOUT", "message": "工具调用超时", "retryable": True}}
    except Exception as e:
        return {"ok": False, "error": {"code": "UPSTREAM_ERROR", "message": str(e)[:200], "retryable": True}}
```

工具异常必须被转成结构化结果喂回模型，让模型自己决定"换个参数重试"还是"告诉用户查不到"。对话绝不因为一个工具报错就整轮崩掉。

### 16.3 系统提示词（6 块）

按固定顺序拼接，每块职责单一、便于单测。

| # | 块 | 内容 | 来源 |
|---|---|---|---|
| 1 | 角色 | 你是中国境内的出行规划助手，用中文回答，输出可执行的行程 | 常量 |
| 2 | 当前时间 | `今天是 2025-03-18 星期二，时区 Asia/Shanghai` | 运行时注入 |
| 3 | 可用工具 | 只列**实际挂载**的工具名与一句话说明 | `build_toolset()` |
| 4 | 用户画像 | `常住上海；预算档位：舒适；节奏：适中；兴趣：历史、博物馆；忌口：不吃辣` | `users.profile` |
| 5 | 工具使用策略 | 见下 | 常量 |
| 6 | 输出要求 | 见下 | 常量 |

**第 5 块：工具使用策略（原文要点）**

1. 涉及具体日期和目的地，**先调 `weather_forecast`**，天数要覆盖行程天数。用户没给日期就先问，或按"本周末"默认并说明。
2. 目的地必须先 `place_search` 拿真实 POI，**不要凭记忆写景点名**。
3. 相邻景点调用 `route_plan` 算真实耗时，不要凭感觉估。
4. 政策类问题（要不要预约、限行、门票）先调 `search_knowledge_base`。
5. 工具返回 `ok=false` 时**如实说明**查不到，不要假装成功，也不要把错误码抛给用户。
6. 营业时间、票价、评分缺失时说"未获取到"，**绝对不要编造**。
7. 单轮工具调用不超过 8 次。

**第 6 块：输出要求（原文要点）**

1. 先 2–4 句自然语言总结（目的地、日期、人数、预算、天气结论、关键约束），**不要复述工具原始 JSON**。
2. 然后按天输出 Markdown 时间轴，**同时**给出结构化行程 JSON（见 16.4）供前端渲染卡片。
3. 天气信息必须来自 `weather_forecast`，注明数据发布时间。
4. 用了知识库就在句末标 `[doc:文档标题]`。
5. 结尾给 1–3 条风险提示（雨天备选、预约要求、体力强度）。
6. 价格一律标注"为估算值，实际以现场为准"。

> **Prompt 缓存优化**：第 1、5、6 块是常量，放最前面且顺序固定，便于命中 DeepSeek 的前缀缓存降本。第 2、3、4 块是变量，放常量之后。

### 16.4 行程 JSON Schema

前端卡片、Markdown 导出共用这一个结构。

```json
{
  "title": "杭州周末 2 日游",
  "destination": { "name": "杭州市", "adcode": "330100", "location": "120.153576,30.287459" },
  "start_date": "2025-03-22",
  "end_date": "2025-03-23",
  "day_count": 2,
  "travelers": { "adults": 2, "children": 0 },
  "budget": {
    "currency": "CNY",
    "total_cent": 150000,
    "breakdown": {
      "transport_cent": 40000, "lodging_cent": 50000,
      "food_cent": 30000, "tickets_cent": 20000, "other_cent": 10000
    }
  },
  "summary": "两天以西湖环线为核心，周六天气好安排户外，周日有雨改室内。",
  "days": [
    {
      "date": "2025-03-22",
      "weekday": "星期六",
      "theme": "西湖环线",
      "weather": { "condition": "多云", "temp_low_c": 18, "temp_high_c": 24 },
      "items": [
        {
          "index": 1,
          "start_time": "09:00",
          "end_time": "11:30",
          "type": "attraction",
          "title": "断桥残雪 → 白堤 → 孤山",
          "location": {
            "name": "断桥残雪",
            "address": "西湖区北山街",
            "location": "120.141872,30.259636"
          },
          "duration_min": 150,
          "cost_cent": 0,
          "transport": { "mode": "walking", "duration_min": 5, "distance_m": 380 },
          "notes": "建议 9 点前到，10 点后人流明显增多",
          "source": "tool"
        },
        {
          "index": 2,
          "start_time": "12:00",
          "end_time": "13:00",
          "type": "meal",
          "title": "午餐：知味观（仁和路店）",
          "location": {
            "name": "知味观",
            "address": "上城区仁和路83号",
            "location": "120.169311,30.245922"
          },
          "duration_min": 60,
          "cost_cent": 16000,
          "transport": { "mode": "walking", "duration_min": 12, "distance_m": 900 },
          "notes": "人均约 80 元",
          "source": "tool"
        }
      ]
    }
  ],
  "packing_list": ["雨伞", "舒适步行鞋"],
  "risks": [
    { "type": "weather", "description": "周日阵雨，户外项目受限",
      "mitigation": "已安排室内备选：浙江省博物馆" }
  ],
  "generated_at": "2025-03-18T02:05:11Z"
}
```

**字段约束表**

| 路径 | 类型 | 必有 | 约束 |
|---|---|---|---|
| `title` | string | 是 | 2–40 字符 |
| `destination.name` | string | 是 | 城市名 |
| `destination.adcode` | string | 是 | 6 位数字 |
| `destination.location` | string | 是 | `"lng,lat"` |
| `start_date` / `end_date` | string | 是 | `YYYY-MM-DD`，`end >= start` |
| `day_count` | int | 是 | 1–30，必须 `== days.length` |
| `travelers.adults` | int | 是 | ≥1 |
| `travelers.children` | int | 是 | ≥0 |
| `budget.currency` | string | 是 | ISO 4217 |
| `budget.total_cent` | int | 是 | ≥0 |
| `budget.breakdown.*` | int | 是 | ≥0；五项之和允许与 `total_cent` 有 ≤5% 偏差（估算） |
| `summary` | string | 是 | 20–600 字符 |
| `days[]` | array | 是 | 长度 == `day_count` |
| `days[].date` | string | 是 | 连续递增，不跳日 |
| `days[].weekday` | string | 是 | 与 `date` 一致 |
| `days[].theme` | string | 是 | ≤20 字符 |
| `days[].weather` | obj \| null | 是 | 来自工具，可为 `null` |
| `days[].items[]` | array | 是 | 1–20 条 |
| `items[].index` | int | 是 | 从 1 递增 |
| `items[].start_time` / `end_time` | string \| null | 是 | `HH:MM`；全天活动用 `null` |
| `items[].type` | enum | 是 | `attraction`/`meal`/`transport`/`rest`/`activity`/`lodging` |
| `items[].title` | string | 是 | 1–60 字符 |
| `items[].location.name` | string | 是 | 地点名 |
| `items[].location.address` | string \| null | 是 | 地址 |
| `items[].location.location` | string \| null | 是 | 坐标；缺失时导出不写地理信息 |
| `items[].duration_min` | int | 是 | 1–720 |
| `items[].cost_cent` | int | 是 | ≥0，0 表示免费 |
| `items[].transport` | obj \| null | 是 | 无转场时为 `null` |
| `items[].transport.mode` | enum | 是 | `walking`/`driving`/`transit` |
| `items[].transport.duration_min` / `distance_m` | int | 是 | ≥0 |
| `items[].notes` | string | 是 | ≤300 字符，可为空串 |
| `items[].source` | enum | 是 | `tool` / `rag` / `model` |
| `packing_list[]` | array | 是 | 0–15 项 |
| `risks[].type` | enum | 是 | `weather`/`reservation`/`safety`/`budget`/`physical` |
| `risks[].mitigation` | string | 是 | ≤200 字符 |
| `generated_at` | string | 是 | ISO-8601 UTC |

> **`source` 字段是抑制幻觉的关键。** 它让前端能把"模型推断、没有数据支撑"的内容加灰底标记。这比在提示词里写"别编造"有效得多——因为用户看得见。

### 16.5 结构化输出与兜底

不指望模型"自觉输出合法 JSON"，三段兜底：

| 顺序 | 做法 |
|---|---|
| 1 | 从回复文本中提取 ` ```json ` 代码块，`json.loads` + Pydantic 校验 |
| 2 | 失败则做常见修复（去尾随逗号、中文引号换英文）再校验一次 |
| 3 | 仍失败 → `itinerary = null`，**只返回文本**，前端不渲染卡片。用户看不到任何报错 |

**能自动修的就修**（`agent/itinerary.py`）

| 检查 | 修正动作 |
|---|---|
| `day_count != days.length` | 以 `days.length` 为准覆盖 |
| 日期跳日 | 补一个 `theme="自由活动"` 的空日 |
| `items[].index` 不连续 | 重排 |
| `end_time <= start_time` | `end_time = null`，`notes` 追加"时间待定" |
| `weekday` 与 `date` 不符 | 按 `date` 重算 |
| `sum(breakdown)` 与 `total_cent` 偏差 > 5% | 用 breakdown 之和覆盖 total |
| `days[].weather` 与工具返回不一致 | **以工具返回为准**覆盖 |

> 原则：**能修的修，修不了就丢行程对象，但绝不丢文本。** 最差情况只是没有卡片。

### 16.6 上下文装配

```
系统提示词（6 块）
  + 历史消息（最近 20 条，只取 user/assistant）
  + 本轮用户消息
```

| 规则 | 值 |
|---|---|
| 历史条数上限 | 20 |
| 最近 4 条永不裁剪 | 保证多轮追问连贯 |
| 历史中的 `itinerary` | **不注入**（太长），只注入其 `title` 和 `summary` |
| `failed` 的消息 | 以 `[上一轮生成失败]` 占位注入，让模型知道 |
| 引用 | 不注入，但上一轮的引用标题会以一句话罗列，便于延续引用 |

### 16.7 会话标题生成

**触发**：会话首条助手消息 `completed` 之后，**异步执行**（不阻塞响应）。

| 项 | 规定 |
|---|---|
| 输入 | 首条用户消息（≤500 字符）+ 行程 `title`（若有） |
| 方法 | 一次小 LLM 调用，`temperature=0` |
| 提示词 | "用不超过 15 个汉字概括这次出行需求，只输出标题本身，不要引号和句号" |
| 结果 | 裁剪到 60 字符，写入 `conversations.title`，`updated_at` 不变 |
| 失败兜底 | 用首条用户消息前 20 字符 |
| 用户改名后 | 不再覆盖（实现：只在 `title == '新对话'` 时才生成） |

### 16.8 用户画像抽取（可选，Demo 可先不做）

画像自动抽取容易抽错，**建议 Demo 阶段先只做手填**（`PUT /auth/profile`），确认体验后再加自动抽取。

若要做，规则如下：

| 项 | 规定 |
|---|---|
| 触发 | 每轮 `done` 后异步 |
| 输入 | 本轮用户消息 |
| 输出 | 结构化：`{"preferences": [{"key": "...", "value": ...}]}` |
| 白名单 | `home_city`/`budget_level`/`pace`/`interests`/`dietary`/`avoid` |
| 写入 | 与现有 `profile` 合并（数组项 union 去重） |
| 频控 | 单轮最多 3 条；出错静默失败，只记 WARNING |

### 16.9 失败处理

| 失败点 | 处理 |
|---|---|
| LLM 超时（60 秒） | 重试 1 次；仍失败 → 消息 `failed`，`LLM_TIMEOUT` |
| LLM 报错/429 | 消息 `failed`，`LLM_FAILED` |
| 工具超时 | 返回 `ok=false/TIMEOUT` 给模型，**不中断对话** |
| 工具异常 | 同上，转成结构化错误 |
| 达到 `max_iterations` | 强制收尾，把已有文本作为回复，`status=completed`，末尾追加"（本轮工具调用次数已达上限，如需更细的规划请继续追问）" |
| 输出被截断（`finish_reason=length`） | 保留已生成内容，`done` 照常 |
| 数据库写失败 | 回滚，`done.status=failed`，已推送内容不回撤 |

---

## 17. RAG 实现

### 17.1 流水线（同步执行）

```
上传 / URL
  → 校验（扩展名、大小、魔数）
  → 落盘 data/uploads/{document_id}/
  → 解析成纯文本
  → 清洗（压空白、去零宽字符、去重复页眉页脚）
  → 分块（800 字，重叠 120，中文优先按句号切）
  → BGE-M3 批量嵌入
  → 写 Chroma（id = "{document_id}:{ordinal}"）
  → 写 rag_documents（status=ready）
  → 返回 chunk_count + chunk_preview
```

**失败回滚**：进入写 Chroma **之前**先按 `document_id` 清一次（保证重跑从干净状态开始）；任一步失败则删除已写入的向量，`status=failed` 并写 `error` 文案。

Demo 不做异步任务、不做进度轮询、不做任务队列。等就等了。

### 17.2 解析器

| 格式 | 解析 | 要点 |
|---|---|---|
| `.pdf` | pypdf 逐页 | 保留页码写进块 metadata；全文提取 < 50 字符 → 判定扫描件 → `status=failed` + "可能是扫描版 PDF，请先 OCR" |
| `.docx` | python-docx | 段落拼接 |
| `.md` / `.txt` | 直接读 UTF-8 | 读失败尝试 GBK，再失败报 `RAG_EMPTY_TEXT` |
| `.csv` | 每行转 `列名: 值` 文本 | 表头当键 |
| URL | trafilatura | 自动去导航/广告；失败退回 beautifulsoup4 取正文 |

**不做的事**：不改写、不摘要、不翻译。RAG 正文必须与原文一致，否则引用对不上。

### 17.3 清洗规则

| 规则 | 说明 |
|---|---|
| 空白归一 | 连续空格/Tab 压成一个；3 个以上换行压成 2 个 |
| 去零宽字符 | 移除 `\u200b-\u200f`、`\ufeff` |
| 去页眉页脚 | 同一行在 >50% 页面重复出现则整行删除 |
| 长度下限 | 清洗后 < 50 字符 → `RAG_EMPTY_TEXT` |
| 长度上限 | 单文档 > 2,000,000 字符只保留前 200 万并记 WARNING |

### 17.4 分块

| 参数 | 值 |
|---|---|
| 大小 | 800 字符（`TPA_RAG_CHUNK_SIZE`） |
| 重叠 | 120 字符 |
| 分隔符优先 | `["\n\n", "\n", "。", "！", "？", "；", "，", " "]` |
| 最小块 | 100 字符（不足与下一块合并，末块除外） |
| 按字符而非 token 切 | 中文按字符更直观，也免装 tokenizer |

用 `langchain.text_splitter.RecursiveCharacterTextSplitter`，`length_function=len`。

**块 metadata（写入 Chroma）**

```json
{
  "document_id": "d_01",
  "title": "杭州西湖景区预约须知",
  "ordinal": 3,
  "page": 2
}
```

`document_id` / `title` / `ordinal` 是**必需**字段（检索后要回填引用）。

### 17.5 嵌入

| 项 | 配置 |
|---|---|
| 模型 | `BAAI/bge-m3`，1024 维 dense |
| 归一化 | 开（余弦相似度等价点积） |
| 批量 | 16 |
| 查询前缀 | **不加**。`bge-m3` 不需要 `query:`/`passage:` 前缀（那是 `bge-v1.5` 的用法） |
| 加载 | 首次使用懒加载（`@lru_cache`），失败则 RAG 不可用但不影响主服务启动 |
| 超长文本 | 800 字符的块远低于模型 8192 token 上限，无需截断 |

模型约 2.3 GB，首次运行从 HuggingFace 下载。离线部署需预下载并把 `TPA_RAG_EMBEDDING_MODEL` 指向本地目录。

**嵌入必须串行**：模型不是线程安全的，用全局锁保证同一时刻只有一个嵌入任务。

### 17.6 Chroma 存储

| 项 | 规定 |
|---|---|
| 客户端 | `PersistentClient(path=data/chroma)` |
| Collection | `tpa_knowledge`，`metadata={"hnsw:space": "cosine"}` |
| 向量 ID | `f"{document_id}:{ordinal}"` |
| `documents` | 块正文（Chroma 内部也存一份，检索后不必回查 SQLite） |
| `metadatas` | 见 17.4 |
| `embedding_function` | **不使用**（我们显式传向量，控制权在自己手里） |
| 删除 | `collection.delete(where={"document_id": {"$eq": doc_id}})` |

> **SQLite 是权威源，Chroma 只是索引。** 检索命中后要校验 `document_id` 在 `rag_documents` 里存在且 `status=ready`，否则丢弃该命中——防止已删文档的内容被喂给模型。

### 17.7 检索

```
query → 嵌入 → Chroma top_k*2 → 阈值过滤 → 按文档去重 → 截断 top_k → Citation[]
```

| 项 | 值 |
|---|---|
| 候选放大 | `top_k * 2`（过滤后仍够数） |
| 阈值 | `score < 0.30` 丢弃 |
| 去重 | 同一文档最多留 2 块，保留分数最高的 |
| 二次校验 | `document_id` 必须存在于 `rag_documents` 且 `status=ready` |
| 空结果 | 返回 `hits: []`，**不是错误**。模型应说"知识库里没有相关信息" |

**为什么先取 2 倍**：阈值过滤和文档去重会砍掉一部分，只取 `top_k` 个原始命中，过滤完可能只剩 1–2 条。放大候选再收敛，召回更稳。

**Citation 结构**

```json
{
  "document_id": "d_01",
  "title": "杭州西湖景区预约须知",
  "ordinal": 3,
  "score": 0.8123,
  "snippet": "自 2025 年 3 月 1 日起，西湖景区实行分时段预约……"
}
```

`snippet` 截断到 200 字符。

**不做**：rerank、hybrid 检索。千级文档量下 dense 检索够用，引入 reranker 要多加载一个模型、增加 100–300ms 延迟，Demo 不值得。

### 17.8 检索效果不好怎么调（实操手册）

| 现象 | 先看什么 | 怎么调 |
|---|---|---|
| 库里明明有，搜不到 | `/rag/search` 的 `hits` 和 `score`。若在 0.3–0.5 徘徊 | 阈值降到 0.2；确认原文说法是否一致 |
| 片段太碎，语义不完整 | 上传返回的 `chunk_preview` | `TPA_RAG_CHUNK_SIZE` 调到 1000–1200 |
| 一页塞了多个主题 | 同上 | 调小 `chunk_size`，优先按空行切 |
| 检索到了但模型不用 | 回复里有没有 `[doc:...]` | 加强提示词第 4 条；检查片段是否被历史窗口挤掉 |
| 总是命中过期政策 | —— | root 手动删除过期文档（**没有版本管理**） |

---

## 18. 启动与运维

### 18.1 首次启动顺序

```
1. pip install -r requirements.txt
2. cp .env.example .env，填 4 个必填项
3. python scripts/init_db.py     # 建表 + 创建 root（幂等）
4. uvicorn backend.main:app --reload --port 8000
```

**`scripts/init_db.py` 做三件事**

1. `Base.metadata.create_all()`（Demo 不用 Alembic）
2. 按 `TPA_ROOT_USERNAME` 查 `users`：不存在则创建为 `role=root, status=active`；已存在则打印"root 已存在，跳过"，**不覆盖密码**
3. 打印创建结果与登录提示

### 18.2 `lifespan` 要做的事

```python
@asynccontextmanager
async def lifespan(app):
    await init_db()                    # 1. 建表（幂等）
    await ensure_root()                # 2. 种子 root
    await heal_stale_messages()        # 3. 把 pending 消息标 failed
    app.state.mcp = await MCPManager.start()   # 4. 拉起两个 MCP 子进程
    yield
    await app.state.mcp.shutdown()     # 5. 关闭子进程
```

**第 3 步很重要**：服务重启后界面不会卡在"生成中"。

```python
# heal_stale_messages
UPDATE messages SET status='failed' WHERE status='pending';
```

### 18.3 日志

| 级别 | 什么时候打 |
|---|---|
| INFO | 请求摘要（方法、路径、状态、耗时）、启动信息、MCP Server 连接成功 |
| WARNING | 工具失败、可恢复异常、标题生成失败 |
| ERROR | LLM 不可用、DB 写失败、MCP 反复崩溃、高德 Key 失效 |

**必须脱敏**：`password`、`token`、`authorization`、URL 中的 `key=`、消息正文（只记长度 `content_len`，不记内容）。

Demo 用 Python 标准 `logging` + 简单 formatter 即可，不引入 structlog。

### 18.4 MCP 子进程管理要点

| 要点 | 做法 |
|---|---|
| 启动 | `mcp.client.stdio.stdio_client` + `ClientSession`，`env` 只传 `TPA_AMAP_KEY`、`TPA_AMAP_TIMEOUT`、`PYTHONPATH` 白名单 |
| 探测 | 启动后调 `initialize` + `tools/list`，20 秒超时；失败不阻塞主服务启动 |
| 工具表 | `dict[str, Tool]`，启动时构建一次 |
| 调用 | `session.call_tool(name, arguments)`，外层 `asyncio.wait_for(15)` |
| 关闭 | `SIGTERM`，3 秒未退则 `kill()` |
| 崩溃 | 捕获后重启，最多 3 次；超了标记 `failed`，`/tools` 里 `degraded=true` |

### 18.5 健康检查（可选但强烈建议）

```python
@app.get("/healthz")
async def healthz():                 # 不查依赖，进程活着就 200
    return {"status": "ok"}

@app.get("/readyz")
async def readyz():                  # 查 DB 与 MCP
    ...
```

自己不写也可以，但**手工验收到第 12 章那条"停掉 place-mcp 后仍能对话"时**，有个 `/tools` 接口就够判断了。

### 18.6 常见问题

| 现象 | 原因 |
|---|---|
| MCP Server 起不来，日志有 JSON 解析错 | 工具里用了 `print()`。**只能写 stderr** |
| 工具总返回 `TOOL_UNAVAILABLE` | 子进程没起来。看后端启动日志里的子进程 stderr 输出 |
| 首次上传文档卡很久 | BGE-M3 正在加载/下载模型，正常。后续会快 |
| 模型不调工具、直接编答案 | 提示词约束不够强，或模型不支持 function calling（别用 `deepseek-reasoner`） |
| 界面一直"生成中" | 服务重启了。启动自愈会把 `pending` 标 `failed`，刷新即可 |
| 行程卡片不出现 | 模型没输出 ```json 代码块。看日志有没有"itinerary 解析失败" |
| 删除会话后消息还在 | `PRAGMA foreign_keys` 没开。改在 service 里显式两步删除 |
| 高德返回全空 | Key 类型不是「Web 服务」，或没开对应 API 权限 |

---

### 18.7 后续升级路径（Demo 之后）

Demo 跑通后如果要做成能上线的产品，按这个顺序补。每项都是独立改造，互不阻塞：

| 优先级 | 补齐项 | 改造点 |
|---|---|---|
| P0 | 登录失败计数与账号锁定 | `api/auth.py` + `users` 加两列 |
| P0 | 限流 | 中间件；或反向代理层做 |
| P0 | refresh token | `security.py` + 新增 `refresh_tokens` 表 |
| P1 | 审计日志 | 新增 `audit_logs` 表 + 中间件 |
| P1 | RAG 异步入库 + 进度查询 | 新增 `jobs` 表 + 后台任务 |
| P1 | 工具调用独立落表 | 新增 `tool_invocations` 表，支持按工具统计 |
| P2 | 游标分页 | `messages` 按 `seq` 翻页 |
| P2 | ICS 日历导出 | `export_service.py` + `icalendar` |
| P2 | 画像自动抽取 | `agent/` 加一次抽取调用 |
| P3 | 熔断 / 缓存 / 告警 | `mcp_servers/common/` |
| P3 | 多实例部署 | 限流与并发锁迁 Redis、DB 迁 PostgreSQL |

---

**文档结束。**

> 改接口、改字段、加错误码，先改本文档再改代码。前端与测试文档都以本文档为准。

