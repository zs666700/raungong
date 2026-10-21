# 出行计划智能助手 —— 测试文档

| 项 | 内容 |
|---|---|
| 适用范围 | 测试工程师、开发自测 |
| 版本 | Demo v1.0 |
| 测试框架 | pytest + pytest-asyncio + respx（Mock 高德） |
| 代码量估算 | 约 400–500 行测试代码 |
| 契约依据 | [后端文档](BACKEND.md) |

> **Demo 的测试目标不是覆盖率，是"演示当天不出丑"**。所以重点放在：
> ① 一条冒烟脚本能 30 秒内判断环境是否正常；② 一份手工验收清单覆盖全部演示动作；③ 高频故障有排查手册。

---

## 目录

- [1. 测试范围与原则](#1-测试范围与原则)
- [2. 测试分层](#2-测试分层)
- [3. 冒烟脚本](#3-冒烟脚本)
- [4. 接口自动化测试](#4-接口自动化测试)
- [5. Mock 策略](#5-mock-策略)
- [6. 手工验收清单](#6-手工验收清单)
- [7. 故障演练](#7-故障演练)
- [8. 演示脚本](#8-演示脚本)
- [9. 排查手册](#9-排查手册)
- [10. 交付前检查](#10-交付前检查)

---

## 1. 测试范围与原则

### 1.1 测什么

| 优先级 | 内容 | 方式 |
|---|---|---|
| P0 | 环境能否起来（依赖、配置、MCP、LLM、高德） | 冒烟脚本 |
| P0 | 20 个接口的 200 与主要 4xx 分支 | pytest |
| P0 | 权限：越权、跨用户、root 专属 | pytest |
| P0 | 演示全流程能走通 | 手工验收 |
| P1 | 工具 JSON 信封结构与字段类型 | pytest 契约断言 |
| P1 | 行程 JSON 校验与自动修正 | pytest 单测 |
| P1 | 关掉一个 MCP Server 后仍能对话 | 手工演练 |
| P2 | 前端页面能渲染、能流式输出 | 手工验收 |
| P2 | 导出 Markdown 内容正确 | 手工验收 |

### 1.2 不测什么（Demo 明确跳过）

| 跳过 | 原因 |
|---|---|
| 覆盖率目标 | 不追求数字，只测关键路径 |
| 性能压测 | 单机 Demo，无并发要求 |
| 并发/竞态测试 | 除"同会话并发"外不测 |
| 安全渗透 | 只做基本的权限与 SSRF 校验 |
| 前端自动化（Playwright） | 手点更快，且 UI 还在改 |
| 浏览器兼容性 | 只保证 Chrome/Edge |
| MCP Server 进程崩溃恢复 | 只手工演练一次 |

### 1.3 三条原则

1. **CI / 自动化测试里绝不打真实网络。** 高德和 LLM 全部 Mock，用录制好的 fixture。
2. **每个 bug 修复带一个回归用例。** Demo 阶段 bug 会集中爆发，没有回归会很痛苦。
3. **手工验收清单必须真的走一遍。** 不能靠"代码看起来没问题"。

---

## 2. 测试分层

```
┌─────────────────────────────────────────────┐
│ 手工验收（演示当天走的全流程）                │  ← 最重要
├─────────────────────────────────────────────┤
│ 故障演练（关掉依赖看降级）                    │
├─────────────────────────────────────────────┤
│ 接口测试（pytest，Mock 高德与 LLM）           │  ~20 个用例
├─────────────────────────────────────────────┤
│ 单元测试（纯函数：行程修正、天气建议、信封）    │  ~15 个用例
├─────────────────────────────────────────────┤
│ 冒烟脚本（判断环境是否正常）                  │  ~4 个步骤
└─────────────────────────────────────────────┘
```

**执行顺序**：冒烟 → 单测 → 接口测试 → 手工验收 → 故障演练。

冒烟不过，后面全是白费。

---

## 3. 冒烟脚本

**文件**：`scripts/smoke.py`
**目标**：30 秒内回答"这个环境能不能跑起来"。
**特点**：不需要起服务、不需要起前端，直接跑脚本。

### 3.1 四步检查

```bash
python scripts/smoke.py
```

输出样例：

```
[1/4] 数据库 ......................... OK  (4 张表，root 已存在)
[2/4] MCP Servers .................... OK  (weather 2 工具 / place 3 工具)
[3/4] 高德 API ....................... OK  (杭州 22℃ 多云，271ms)
[4/4] LLM 调用 ........................ OK  (模型调用了 weather_now，8421ms)

通过 4/4。可以启动服务了。
```

### 3.2 各步实现要点

| 步骤 | 做什么 | 失败时的提示 |
|---|---|---|
| 1 | 连 SQLite，检查 4 张表存在；查 root 用户存在 | `初始化数据库：python scripts/init_db.py` |
| 2 | 拉起两个 MCP Server，`initialize` + `tools/list`，断言工具数为 2 和 3 | 打印子进程 stderr 的最后 20 行（**这是排障的关键**） |
| 3 | 直接调一次 `weather_now(杭州)`，断言 `ok=true` 且 `data.temperature_c` 是 int | 按 infocode 提示：`10001` → Key 错；`10003/10004` → 配额；连接超时 → 网络或代理 |
| 4 | 用 LangChain 跑一次"杭州今天天气怎么样"，断言模型发起了工具调用 | 提示：模型不支持 function calling（别用 `deepseek-reasoner`），或 Key 无效 |

### 3.3 第 2 步为什么必须打印 stderr

MCP 子进程用 **stderr** 打日志（stdout 是协议通道）。子进程起不来时，错误信息全在 stderr 里。冒烟脚本不打印它，你只能看到一个 `TOOL_UNAVAILABLE`，然后一无所知。

```python
if proc.returncode not in (None, 0) or not tools:
    err = (await proc.stderr.read()).decode("utf-8", "ignore")
    print(err[-2000:])          # 最后 2000 字符通常就够定位
```

### 3.4 第 4 步怎么断言"调用了工具"

```python
# 关掉自动降级，只测"模型是否会主动调工具"
answer = await agent.ainvoke({"messages": [("user", "杭州今天天气怎么样")]})
tool_called = any(
    getattr(m, "tool_calls", None) for m in answer["messages"]
)
assert tool_called, "模型没有调用任何工具，检查提示词或模型是否支持 function calling"
```

不要断言"回答里有没有 22℃"——那是内容断言，脆弱且容易误报。只断言**行为**（有没有调工具）。

---

## 4. 接口自动化测试

### 4.1 目录

```
tests/
├─ conftest.py                # fixture：临时库、临时 Chroma、app、token
├─ fixtures/
│  ├─ amap_weather_now.json
│  ├─ amap_weather_forecast.json
│  ├─ amap_place_text.json
│  ├─ amap_geocode.json
│  ├─ amap_error_10001.json        # Key 失效
│  ├─ amap_error_10004.json        # 限流
│  ├─ sample.md                    # 用作 RAG 上传样本
│  └─ itinerary_valid.json
├─ test_auth.py
├─ test_conversations.py
├─ test_tools_contract.py
├─ test_itinerary.py
├─ test_rag.py
└─ test_permissions.py
```

### 4.2 `conftest.py` 关键 fixture

| fixture | 作用 |
|---|---|
| `tmp_data` | 临时数据目录（`app.db` + `chroma/` + `uploads/`），每个测试独立 |
| `app` | 用测试配置构建的 FastAPI 应用，`lifespan` 里 **不拉 MCP 子进程**（用假工具表代替） |
| `client` | `httpx.AsyncClient(transport=ASGITransport(app))` |
| `user_token` | 预置普通用户，返回带 `Authorization` 头的 dict |
| `root_token` | 预置 root 用户 |
| `fake_llm` | 可注入回复序列的 LLM 桩 |
| `mock_amap` | `respx` router，按 URL 路径返回对应 fixture |
| `fake_embedder` | 返回固定维（1024）确定性向量的嵌入桩，**不加载 BGE-M3** |

**两个 fixture 的坑**

```python
# 坑 1：app 的 lifespan 不要拉真 MCP
# 测试里用 monkeypatch 把 mcp_manager.start 换成返回假的工具表：
@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(MCPManager, "start", lambda self: FakeMCPManager())
    ...

# 坑 2：嵌入维度必须和真模型一致（1024）
# 否则测不出"维度不一致导致检索全空"这类问题
class FakeEmbedder:
    dimension = 1024
    def embed_query(self, text): return [hash_to_floats(text, 1024)]
```

### 4.3 用例清单（20 个，够用）

**`test_auth.py`**

| # | 用例 | 断言 |
|---|---|---|
| A1 | 注册新用户 | 201，返回 `token`，`user.role == "user"` |
| A2 | 重复用户名注册 | 409，`AUTH_USERNAME_TAKEN` |
| A3 | 密码少于 8 位 | 400，`AUTH_WEAK_PASSWORD` |
| A4 | 登录成功 | 200，返回 `token` |
| A5 | 密码错误 | 401，`AUTH_BAD_CREDENTIALS` |
| A6 | 用错误 token 访问 `/auth/me` | 401，`AUTH_TOKEN_INVALID` |
| A7 | 已禁用用户登录 | 403，`AUTH_DISABLED` |
| A8 | 更新画像 | 200，`profile` 被整体替换（旧键消失） |

**`test_conversations.py`**

| # | 用例 | 断言 |
|---|---|---|
| C1 | 建会话 | 201，`title == "新对话"` |
| C2 | 列表只返回自己的 | 用户 A 建 2 个、B 建 1 个 → A 拿到 2 个 |
| C3 | 访问他人会话详情 | 404，`NOT_FOUND`（不是 403） |
| C4 | 改标题 | 200，`title` 已更新 |
| C5 | 删会话后消息也删 | 删完查 `messages` 表为空（**验证级联**） |
| C6 | 非流式发消息 | 200，`assistant_message.seq == user_message.seq + 1` |

**`test_permissions.py`**

| # | 用例 | 断言 |
|---|---|---|
| P1 | 普通用户访问 `/rag/documents` | 403，`FORBIDDEN` |
| P2 | 普通用户访问 `/admin/users` | 403，`FORBIDDEN` |
| P3 | root 访问自己的会话 | 200（root 不继承数据豁免，但这是自己的） |
| P4 | root 访问他人会话 | 404（**不是 200**） |
| P5 | root 禁自己 | 403 |
| P6 | root 降级最后一个 root | 403 |

**`test_tools_contract.py`**

| # | 用例 | 断言 |
|---|---|---|
| T1 | 5 个工具的成功返回都合规 | `ok == True`，`error is None`，`data` 是 dict |
| T2 | 5 个工具的失败返回都合规 | `ok == False`，`data is None`，`error` 有 `code/message/retryable` |
| T3 | 双写一致 | `json.loads(content[0]["text"]) == structuredContent` |
| T4 | 字段类型 | `*_cent`/`*_m`/`*_s` 是 int；温度是 int；日期格式匹配 `\d{4}-\d{2}-\d{2}` |
| T5 | 空值显式 | 高德返回 `"tel": []` 时，输出里 `tel is None` 而非缺失键 |
| T6 | 高德 10001 | 返回 `UPSTREAM_AUTH_FAILED`，`retryable == False` |
| T7 | 高德 10004 | 返回 `UPSTREAM_RATE_LIMITED`，`retryable == True` |

**`test_itinerary.py`**

| # | 用例 | 断言 |
|---|---|---|
| I1 | 合法 JSON | 解析成功，`day_count == len(days)` |
| I2 | `day_count` 与 `days` 不符 | 自动修正为 `len(days)` |
| I3 | 日期跳日 | 自动补一个空日 |
| I4 | `end_time` 早于 `start_time` | 置 `null` |
| I5 | 非法 JSON | 返回 `None`（**不抛异常**） |
| I6 | 代码块包裹的 JSON | 能正确提取 |

**`test_rag.py`**

| # | 用例 | 断言 |
|---|---|---|
| R1 | 上传 md 文件 | 201，`status == "ready"`，`chunk_count > 0` |
| R2 | 上传不支持的类型 | 400，`RAG_FILE_TYPE` |
| R3 | 上传空文件 | 201，`status == "failed"`，`error` 非空 |
| R4 | 检索能命中 | `hits` 非空，`score > 0` |
| R5 | 删除文档后检索不到 | `hits` 为空 |
| R6 | URL 指向 `127.0.0.1` | 400，`RAG_URL_BLOCKED` |

### 4.4 一个完整用例示例

```python
@respx.mock
@pytest.mark.asyncio
async def test_weather_forecast_contract(client, user_token, mock_amap):
    mock_amap.weather_forecast()                      # 返回 fixture

    resp = await client.post("/api/v1/tools/weather_forecast/invoke",
                             json={"args": {"city": "杭州", "days": 2}},
                             headers=user_token)
    assert resp.status_code == 200

    body = resp.json()
    assert body["ok"] is True

    env = body["data"]["result"]                       # 工具自己的信封
    assert env["ok"] is True
    assert env["error"] is None
    assert env["tool"] == "weather_forecast"
    assert env["provider"] == "amap"

    data = env["data"]
    assert isinstance(data["forecast"], list)
    assert len(data["forecast"]) == 2
    for day in data["forecast"]:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", day["date"])
        assert isinstance(day["day_temp_c"], int)
        assert isinstance(day["night_temp_c"], int)
        assert day["rain_risk"] in ("low", "medium", "high")
        assert day["weekday"] in ("星期一", "星期二", "星期三", "星期四",
                                  "星期五", "星期六", "星期日")
```

---

## 5. Mock 策略

### 5.1 高德：respx 拦截 httpx

```python
# conftest.py
@pytest.fixture
def mock_amap():
    with respx.mock(assert_all_called=False) as router:
        router.get("https://restapi.amap.com/v3/weather/weatherInfo").mock(
            return_value=httpx.Response(200, json=load("amap_weather_forecast.json"))
        )
        router.get("https://restapi.amap.com/v3/place/text").mock(
            return_value=httpx.Response(200, json=load("amap_place_text.json"))
        )
        yield router
```

**Fixture 怎么来**：第一次真实联调时，把响应原样存下来（去掉 `key` 等敏感参数），**不要手写**。手写的 fixture 会和真实结构不一致，测不出真问题。

### 5.2 LLM：FakeListChatModel

```python
from langchain_core.language_models.fake_chat_models import FakeListChatModel

# 场景 1：模型直接回答，不调工具
llm = FakeListChatModel(responses=["杭州明天多云，18-24℃。"])

# 场景 2：模型先调工具再回答（两轮）
llm = FakeListChatModel(responses=[
    '',  # 第一轮返回带 tool_calls 的消息（需要 AIMessage 显式构造）
    '根据预报，杭州明天多云。',
])
```

**更可控的写法**：直接用 `AIMessage` 构造带 `tool_calls` 的响应，比 `FakeListChatModel` 好断言。

### 5.3 嵌入：确定性假向量

CI 不加载 BGE-M3（2.3 GB）。用假嵌入，但要保证：

| 要求 | 原因 |
|---|---|
| `dimension == 1024` | 与真模型一致，否则测不出维度问题 |
| 相同文本 → 相同向量 | 保证检索可重现 |
| 不同文本 → 明显不同向量 | 否则检索全命中或全不命中 |

```python
class FakeEmbedder:
    dimension = 1024

    def embed_query(self, text: str) -> list[float]:
        import hashlib, random
        seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        v = [rng.uniform(-1, 1) for _ in range(self.dimension)]
        norm = sum(x * x for x in v) ** 0.5
        return [x / norm for x in v]
```

### 5.4 不 Mock 的部分

| 不 Mock | 原因 |
|---|---|
| SQLite | 用临时文件即可，Mock 反而失真 |
| Chroma | `PersistentClient` 指向 `tmp_path`，很轻量 |
| 文件解析 | pypdf/python-docx 处理真文件，快且不需要网络 |

---

## 6. 手工验收清单

**这份清单必须真的走一遍。** 每项都要打勾。

### 6.1 环境

- [ ] `python scripts/smoke.py` 输出 `通过 4/4`
- [ ] 后端 `:8000` 起得来，日志无 ERROR
- [ ] 前端 `:8080` 起得来，浏览器能打开
- [ ] 用 `.env` 里的 root 账号能登录

### 6.2 权限

- [ ] root 登录后能看到"知识库""用户"菜单入口
- [ ] 普通用户登录后**看不到**这两个菜单
- [ ] 普通用户直接在地址栏输入 `/knowledge` → 被踢回 `/chat`
- [ ] 普通用户调 `/api/v1/rag/documents`（用 curl 带自己的 token）→ 403
- [ ] root 在用户页能看到用户列表，但**看不到任何对话内容**
- [ ] root 的"禁用自己"按钮是灰的
- [ ] 系统里只有一个 active root 时，那个 root 的"降级"按钮是灰的

### 6.3 对话与流式

- [ ] 新建会话 → 输入"这周末去杭州玩两天，两个人，预算 1500" → 点发送
- [ ] 顶部状态条依次出现"正在思考""正在查询天气预报""正在搜索地点"（顺序可能不同，但能看到变化）
- [ ] 文本**逐字**出现（不是一次性蹦出来）
- [ ] 工具调用面板显示"已调用 N 个工具 · X.Xs"，展开能看到每个工具的耗时和摘要
- [ ] 回复里出现的温度、景点名是**真实数据**（对比高德官网或 `/tools/.../invoke` 的结果）
- [ ] **行程卡片出现**，包含：标题、日期、人数、预算条、按天时间轴
- [ ] 卡片里的金额、时长、地址显示正常（免费项显示"免费"而不是"¥0"）
- [ ] 如果某条 item 标了"模型推断"灰底，说明 `source` 字段生效了

### 6.4 取消与失败

- [ ] 发送后立刻点"停止" → 状态变"已停止生成"，已生成内容保留，输入框恢复可用
- [ ] 再发一条消息，能正常生成（说明锁已释放）
- [ ] 在生成中再点发送 → 提示"正在生成回复，请稍候"

### 6.5 持久化

- [ ] 刷新页面 → 消息还在
- [ ] 重启后端 → 消息还在
- [ ] 侧边栏会话列表显示正确的标题（不是"新对话"）和条数
- [ ] 有行程的会话显示"已生成行程"徽标

### 6.6 导出

- [ ] 点"导出行程" → 浏览器下载 `.md` 文件
- [ ] 打开文件，标题、日期、预算、每天时间轴、风险提示都在
- [ ] 没有行程的会话里，导出按钮不出现（或置灰）

### 6.7 知识库

- [ ] 用 root 上传一份 PDF（或 md）→ 显示 loading → 成功后提示"入库成功，共 N 块"
- [ ] 上传返回的 `chunk_preview` 弹窗内容可读（说明切块正常）
- [ ] 文档列表能看到这条记录，状态 `ready`，块数正确
- [ ] 在检索调试框输入一个文档里明确有的词 → 命中，`score` 显示正常
- [ ] 回到对话，问一个该文档才有的信息（如"西湖要预约吗"）→ 回复里带 `[doc:文档标题]`
- [ ] 删除该文档 → 再检索同一问题 → 检索不到
- [ ] 上传一个不支持的类型（如 `.exe`）→ 提示"不支持该文件类型"
- [ ] 上传一个空的 `.txt` → 列表里出现 `failed` 行并显示原因

### 6.8 用户画像

- [ ] 在偏好页填"常住上海、不吃辣"，保存
- [ ] 新建会话问"推荐点吃的" → 回复里体现"不辣"偏好（或至少没有推荐辣菜）
- [ ] 清空偏好后再问 → 不再体现

### 6.9 前端细节

- [ ] Markdown 正常渲染（标题、列表、加粗）
- [ ] 用户输入里的 HTML/脚本标签**不会被执行**（按纯文本显示）
- [ ] 消息多时能正常滚动，流式追加时自动跟随到底部
- [ ] 手动向上滚动后，流式追加**不**把页面拽回底部（有"回到底部"按钮）

---

## 7. 故障演练

**目的：证明系统在依赖缺失时不会崩，而是优雅降级。**

### 7.1 演练 1：杀掉 `place-mcp`

```bash
# Windows
Get-Process python | Where-Object { $_.CommandLine -like "*mcp_servers.place*" } | Stop-Process

# Linux/macOS
pkill -f "mcp_servers.place"
```

| 预期 | 检查 |
|---|---|
| 后端**不崩** | 后端日志只有 WARNING，进程仍活着 |
| `/api/v1/tools` 里 `place` 状态变 `disconnected` 或 `degraded=true` | curl 一下 |
| 对话页面顶部出现黄色横幅"地点服务暂时不可用" | 视觉检查 |
| 发消息后模型只调天气工具，回复里会说明"无法查询具体景点" | 看回复内容 |
| 对话**不报错**，正常返回文本 | 状态 `completed` |

### 7.2 演练 2：断 WS

| 做法 | 预期 |
|---|---|
| 断开网络 10 秒再恢复 | 顶部出现"连接已断开，正在重连…"، 恢复后自动补拉，消息不丢不重 |
| 生成中刷新页面 | 重连后补拉，能看到完整回复（因为生成在服务端继续） |

### 7.3 演练 3：无效高德 Key

把 `.env` 里 `TPA_AMAP_KEY` 改成一个错的，重启：

| 预期 | 检查 |
|---|---|
| 冒烟脚本第 3 步失败并提示"Key 错或权限不足" | 提示要准确 |
| 工具返回 `UPSTREAM_AUTH_FAILED` | `/tools/weather_now/invoke` |
| `retryable == false`（不重试） | 看 `error.retryable` |
| 后端日志有 ERROR（便于发现） | —— |
| 对话仍能回（走纯 LLM 降级） | 不崩 |

### 7.4 演练 4：LLM Key 无效

| 预期 | 检查 |
|---|---|
| 发消息 → 气泡显示失败 + 重试按钮 | 前端表现 |
| 后端返回 `LLM_FAILED` 或 `LLM_TIMEOUT` | —— |
| 消息 `status=failed` 已落库 | 刷新后仍能看到失败记录 |
| 后端不崩，其他接口正常 | —— |
| 冒烟脚本第 4 步失败并给出准确提示 | —— |

### 7.5 演练 5：生成中重启后端

| 预期 | 检查 |
|---|---|
| 重启后那条消息 `status` 变 `failed`（启动自愈） | 刷新页面看到失败气泡，**不是永久"生成中"** |
| 输入框可用，能继续发消息 | —— |

---

## 8. 演示脚本

**演示前 10 分钟照这个走一遍，确保一切就绪。**

### 8.1 演示前检查（5 分钟）

```bash
# 1. 冒烟
python scripts/smoke.py

# 2. 起服务（两个终端）
uvicorn backend.main:app --port 8000
python -m frontend.main

# 3. 预置数据
#    - 用 root 上传 2 份文档（一份景区政策、一份交通新规）
#    - 在 /rag/search 里各检索一次，确认能命中
#    - 普通用户账号建好，并填好画像（常住上海、不吃辣）
```

### 8.2 演示流程（8 分钟）

| 时间 | 动作 | 说什么 |
|---|---|---|
| 0:00 | 用普通用户登录 | "这是普通用户视角" |
| 0:30 | 新建会话，输入"这周末去杭州玩两天，两个人，预算 1500" | "它自己判断要查天气、查景点、算路线" |
| 0:40 | **指着状态条** | "看，它现在在查天气 —— 这个过程是可见的" |
| 1:30 | 行程卡片出现 | "温度是真的，景点名称是真的，不是编的" |
| 2:00 | 展开工具调用面板 | "4 次工具调用，每次都是真实 API" |
| 2:30 | 点"导出行程" | "可以直接拿到一份可用的行程文档" |
| 3:00 | 追问"周天下雨的话怎么改" | "多轮上下文，它会调整安排" |
| 3:40 | 问"西湖要预约吗" | "这类政策问题它会去查知识库" → **指着引用** |
| 4:20 | 刷新页面 | "全都存下来了，刷新、重启都不丢" |
| 4:40 | 切到 root 账号，进知识库页 | "管理员可以随时上传最新政策，立刻生效" |
| 5:10 | 上传一份新文档 → 检索调试命中 → 回对话再问 | "刚上传的，马上就能回答" |
| 6:00 | 进用户管理页 | "能管用户，但**看不到任何人的对话内容** —— 这是有意的" |
| 6:40 | 停掉 place-mcp，再对话 | "一个服务挂了，整体不挂，会告诉我能力受限" |
| 7:30 | 收尾 | "整个系统：FastAPI + LangChain + MCP 独立进程 + RAG，约 2500 行" |

### 8.3 演示备用问题（如果时间还有）

```
带爸妈去苏州一日游，不想走太多路
下周去成都出差三天，晚上有什么值得去的
帮我对比一下杭州和苏州哪个适合十一去
```

### 8.4 演示兜底

| 如果 | 就 |
|---|---|
| 高德挂了 | 用预先跑好的截图/录屏展示行程卡片；或直接说"现在外部数据源不可用，我们看下已经生成的" |
| LLM 超时 | 换个更短的问题（"杭州今天多少度"），通常更快 |
| 行程卡片没出来 | 明说"模型这次没给出结构化行程，只有文本"，然后重试一次 |
| 全挂了 | 展示预置的会话记录 + 录屏 |

**演示前一定要录一份"完美跑通"的录屏**——这是唯一的保险。

---

## 9. 排查手册

### 9.1 启动类

| 现象 | 排查顺序 |
|---|---|
| 启动直接退出 | 看日志第一行——通常是必填配置缺失（`TPA_JWT_SECRET` / `TPA_ROOT_PASSWORD` / `TPA_LLM_API_KEY` / `TPA_AMAP_KEY`） |
| `sqlite3.OperationalError: unable to open database file` | `TPA_DATA_DIR` 目录不存在。先建目录，或跑 `init_db.py` |
| `ModuleNotFoundError: mcp_servers` | 在错误的工作目录启动。`mcp_servers` 必须在 `PYTHONPATH` 里，从项目根目录启动 |
| 端口被占用 | 换端口，或先杀掉占用的进程 |

### 9.2 MCP 类

| 现象 | 排查 |
|---|---|
| `TOOL_UNAVAILABLE` | ① 后端启动日志里有没有子进程 stderr；② 直接 `python -m mcp_servers.weather` 手动跑，看报什么错 |
| 子进程启动后立刻退出 | **最常见：工具里用了 `print()`**，污染了 stdout 的 JSON-RPC 通道。改成 `logging` 或 `sys.stderr.write` |
| `tools/list` 返回空 | `@mcp.tool()` 装饰器没加，或函数名不符合 `snake_case` |
| 工具调用一直超时 | 高德网络不通（公司代理？）。先用 `curl` 直接测高德接口 |
| 调用返回 `UPSTREAM_AUTH_FAILED` | Key 是「Web 服务」类型吗？在控制台确认 **Key 类型**和**已开通的 API** |

### 9.3 Agent 类

| 现象 | 排查 |
|---|---|
| 模型不调工具、直接编答案 | ① 确认模型名不是 `deepseek-reasoner`；② 看系统提示词有没有真的注入工具清单；③ 看工具 `description` 是否写清楚了用途 |
| 只调一次工具就回答 | 正常。提示词要求"先查天气"已满足；若需要更完整规划，加强第 5 块提示词 |
| 行程卡片不出现 | ① 打印 `itinerary` 是否为 `None`；② 看日志有没有"itinerary 解析失败"；③ 用 `POST /conversations/{id}/messages` 看正文里到底有没有 ```json 块 |
| `CONTEXT_TOO_LONG` 或回答质量突然下降 | 历史 20 条可能太长。降 `TPA_AGENT_HISTORY`（需加配置项），或让用户新建会话 |
| 回答一半断掉 | `finish_reason=length`，`max_tokens` 不够。缩短问题或调大上限 |

### 9.4 前端类

| 现象 | 排查 |
|---|---|
| 登录后一片空白 | 看前端进程日志（不是后端）。通常是模板渲染异常 |
| 一直"生成中" | 后端重启了但前端没感知。刷新页面 |
| WS 连不上 | `TPA_BACKEND_BASE_URL` 写成 `ws://...` 了？应写 `http://...`，代码里从 http 换算成 ws |
| 逐字效果变成一次性蹦出 | 渲染节流没生效，或后端没走流式（检查是不是用了非流式接口） |
| 卡片样式错乱 | 用写死的 `itinerary.json` fixture 单独调样式，别等 LLM |

### 9.5 RAG 类

| 现象 | 排查 |
|---|---|
| 上传成功但检索不到 | ① `/rag/search` 看 `score`；② 阈值 0.3 可能太高，降到 0.2 试；③ 确认文档 `status=ready` |
| `chunk_count` 是 0 | 解析出空文本。看 `error` 字段，或直接 `pypdf` 打开确认有没有文本层 |
| 检索到了但回答不用 | 看提示词第 4 条；看片段是否被历史窗口挤掉；看片段是否真的回答了问题 |
| 删除后还能搜到 | Chroma 删除没生效，或 `document_id` 类型不一致（字符串 vs 其他） |
| 第一次上传特别慢 | BGE-M3 在下载（2.3 GB）。属正常，后续会快 |

---

## 10. 交付前检查

### 10.1 代码

- [ ] `requirements.txt` 里所有版本号已钉死（不用 `latest`）
- [ ] 没有 `print()` 出现在 `mcp_servers/`（会破坏 stdio 通道）
- [ ] 没有硬编码的 Key / 密码 / token
- [ ] `.env` 不在仓库里，`.gitignore` 覆盖了 `.env` 和 `data/`
- [ ] `.env.example` 是完整的，4 个必填项有注释说明
- [ ] 日志里没有 token、密码、消息正文

### 10.2 功能

- [ ] 第 6 章手工验收清单**全部勾选**
- [ ] 第 7 章 5 个故障演练都跑过
- [ ] 冒烟脚本在**干净环境**（删掉 `data/` 重来）能通过

### 10.3 自动化

- [ ] `pytest tests/ -v` 全绿
- [ ] 测试里没有任何真实网络请求（断网也能跑过）
- [ ] 至少覆盖：认证 6 例、权限 6 例、会话 6 例、工具契约 7 例

### 10.4 演示准备

- [ ] 有预置的会话记录（万一现场 LLM 慢）
- [ ] 有预置的知识库文档（2 份以上）
- [ ] 有"完美跑通"的录屏
- [ ] README 里的启动步骤是**照着做能跑通**的（找个没参与开发的人按 README 走一遍）

---

**文档结束。**

> Demo 测试的唯一目标是"演示当天能稳定讲完"。不要为覆盖率写测试，要为"这个流程演示时会坏吗"写测试。
