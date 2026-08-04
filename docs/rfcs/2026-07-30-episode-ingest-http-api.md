# RFC: Episode Ingest HTTP API

- **状态**：已批准（评审修订版）
- **日期**：2026-07-30
- **类型**：公共 API / 实现设计规格
- **关联路线图**：Phase 1 — 生产底座与单 Agent 纵向切片
- **前置依赖**：Episode ingest 应用切片、PostgreSQL 适配器、Composition Root、Outbox Relay

## 1. 背景与动机

EngramMesh 当前已完成记忆写入路径（`RecordEpisodeHandler`）、PostgreSQL 持久化、事务 Outbox 以及 Outbox Relay。外部调用仍依赖 Python 脚本直接调用应用层，缺少可部署的 HTTP 入口。

本切片在模块化单体内部实现 `control_api` 的第一块能力：将 `RecordEpisodeCommand` 暴露为 REST 端点，使 Phase 1 纵向切片具备外部可集成性，并为后续 SDK、E2E 测试和 Demo 提供基础。

## 2. 目标

1. 暴露 `POST /v1/tenants/{tenant_id}/episodes`，映射到已有 `RecordEpisodeHandler`。
2. 提供 `GET /health`（存活探针）和 `GET /ready`（就绪探针，检查 PostgreSQL 连接池）。
3. 通过 `AppRuntime` 组合根装配，HTTP 进程生命周期与现有 bootstrap 一致。
4. 结构化 HTTP 错误映射（403 / 409 / 422 / 503 / 500）。
5. 单元测试、集成测试和 JSON Schema 契约测试覆盖核心路径。

## 3. 非目标

以下能力明确不在本切片范围内，按路线图顺序在后续切片实现：

- OIDC / JWT 鉴权（继续使用 `EnvironmentGatedMemoryAuthorization`）
- Episode 读取 API（`GET` / stream）
- Inbox 消费者与投影 Worker
- HTTP 进程内启动 Outbox relay 后台循环
- 对象存储上传（`content_ref` 由调用方预先提供）
- 生产级 OpenTelemetry metrics、分布式追踪、OpenAPI 发布治理
- PostgreSQL RLS 策略
- TLS 终止（由反向代理负责）
- HTTP 响应体 JSON Schema（v1 仅发布 request schema；响应形状由 Pydantic model 与测试固定）

## 4. 备选方案

| 方案 | 说明 | 未采纳原因 |
|---|---|---|
| **A（采纳）** REST + path `tenant_id` + body `scope.tenant_id` 双重校验 | 多租户 API 常见模式；便于网关路由与审计 | — |
| B 仅 body 含 `tenant_id` | 更简单 | 无法在路由层做租户隔离与限流；与 Phase 1 Control Plane 租户路由不一致 |
| C gRPC | 性能更好 | 超出本切片范围；SDK/E2E 需要额外工具链；架构文档首选 REST/FastAPI |
| D 与 Inbox 打包交付 | 一次闭合事件环路 | 范围过大；HTTP 入口是 Phase 1 纵向切片的前置条件 |

## 5. 架构与分层

### 5.1 依赖方向

```text
HTTP Request (FastAPI)
  → bootstrap/http/schemas.py     # 传输层 Pydantic DTO
  → bootstrap/http/mappers.py     # DTO → RecordEpisodeCommand
  → RecordEpisodeHandler.handle() # 已有应用层，不变
  → PostgresMemoryUnitOfWork      # 已有适配器，不变
```

- FastAPI 与 uvicorn 仅出现在 `bootstrap/http/` 和 `bootstrap/server.py`。
- `modules/memory/` 的 domain、application、ports **不做行为变更**。
- HTTP 层通过 `AppRuntime.record_episode_handler()` 获取 handler，不得直接 import `adapters.postgres`。
- 传输层 DTO 与 application `RecordEpisodeCommand` 分离；mapper 是唯一转换边界。
- **唯一应用工厂**：`create_app(runtime: AppRuntime, *, lifespan)` 为生产与测试共用入口；测试通过 mock `PostgresMemoryDatabase` 或真实 postgres runtime 装配，不维护平行的 `create_test_app(handler)`。

### 5.2 与 `episode-recorded` 事件契约的差异

本切片引入独立的 HTTP 请求契约 `record-episode-request.schema.json`。**不得**复用或 extend `episode-recorded.schema.json` 的 payload scope 定义。

| 层面 | tenant 位置 | scope 字段 |
|---|---|---|
| HTTP 请求体 | `scope.tenant_id`（必填）+ path `tenant_id`（双重校验） | `tenant_id`, `subject_id`, `workspace_id?`, `agent_id?` |
| Outbox 事件 envelope | `tenant_id`（信封层） | — |
| Outbox 事件 payload.scope | **不含** `tenant_id` | `subject_id`, `workspace_id?`, `agent_id?` |

Mapper 职责：

1. 校验 path `tenant_id` 与 body `scope.tenant_id` 一致。
2. 组装 domain `MemoryScope`（含 `tenant_id`）。
3. `RecordEpisodeHandler` 发布 outbox 时，payload.scope **不包含** `tenant_id`（保持现有事件契约与 `test_episode_event_uses_envelope_as_its_only_tenant_authority` 不变）。

path 与 body 双写 `tenant_id` 是刻意的冗余：支持 API Gateway 路由、审计日志与请求体验证，降低「路径租户与载荷租户不一致」的风险。

### 5.3 目录结构

```text
services/src/engrammesh/bootstrap/
  http/
    __init__.py
    app.py          # FastAPI factory（接受 lifespan）
    schemas.py      # RecordEpisodeRequest / RecordEpisodeResponse
    mappers.py      # HTTP DTO ↔ application command
    errors.py       # 异常 → HTTP 响应映射
  server.py         # uvicorn 入口（python -m engrammesh.bootstrap.server）

packages/contracts/jsonschema/memory/v1/
  record-episode-request.schema.json   # HTTP 请求体契约（独立，非事件 payload）

services/tests/
  unit/bootstrap/http/                 # mapper、错误映射单元测试
  integration/http/                  # httpx + create_app(runtime) 集成测试
  contract/                          # JSON Schema 合规测试
```

### 5.4 新增依赖

| 包 | 用途 | 分组 |
|---|---|---|
| `fastapi` | HTTP 框架 | `dependencies` |
| `uvicorn[standard]` | ASGI 服务器 | `dependencies` |
| `httpx` | 测试客户端 | `dev` |

## 6. API 契约

### 6.1 `POST /v1/tenants/{tenant_id}/episodes`

**路径参数**

| 字段 | 类型 | 说明 |
|---|---|---|
| `tenant_id` | UUID | 必须与请求体 `scope.tenant_id` 一致；不一致返回 422 |

**请求头**

| 字段 | 必填 | 说明 |
|---|---|---|
| `X-Correlation-Id` | 否 | 缺省时服务端生成 UUID v4；非 UUID 格式 → 422 `validation_error` |
| `Content-Type` | 是 | `application/json` |

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `actor_id` | UUID | 是 | 执行写入的主体 |
| `scope` | object | 是 | 记忆作用域 |
| `scope.tenant_id` | UUID | 是 | 须与路径 `tenant_id` 一致 |
| `scope.subject_id` | UUID | 是 | 记忆主体 |
| `scope.workspace_id` | string \| null | 否 | 非空字符串 |
| `scope.agent_id` | UUID \| null | 否 | Agent 实例 ID |
| `source_type` | enum | 是 | `user` / `agent` / `tool` / `file` / `system` |
| `content_ref` | UUID | 是 | 内容制品引用（artifact ID） |
| `observed_at` | datetime (RFC 3339, TZ-aware) | 是 | 观测时间 |
| `content_hash` | string | 是 | 非空，如 `sha256:...` |
| `idempotency_key` | string | 是 | 非空，租户内幂等键 |
| `sensitivity` | enum | 是 | `public` / `internal` / `confidential` / `restricted` |
| `retention_class` | enum | 是 | `ephemeral` / `standard` / `extended` / `legal_hold` |
| `consent_basis` | string | 是 | 非空，同意依据 |

**成功响应**

| 状态码 | 条件 | 响应体 |
|---|---|---|
| `201 Created` | `created=true` | `{ "episode_id": "<uuid>", "created": true }` |
| `200 OK` | `created=false`（幂等重放） | `{ "episode_id": "<uuid>", "created": false }` |

**错误响应**

统一错误信封：

```json
{
  "error": {
    "code": "<machine_readable_code>",
    "message": "<human_readable_message>",
    "details": []
  }
}
```

| 状态码 | code | 触发条件 |
|---|---|---|
| `403` | `episode_authorization_denied` | `EpisodeAuthorizationDenied` |
| `409` | `episode_idempotency_conflict` | `EpisodeIdempotencyConflict` |
| `422` | `validation_error` | Pydantic 校验失败、path/body `tenant_id` 不一致、非法 `X-Correlation-Id` |
| `503` | `service_unavailable` | `ConfigurationError`（如 `memory_disabled`、`http_disabled`） |
| `500` | `internal_error` | 未预期异常（不泄漏堆栈） |

`EpisodeAuthorizationDenied` 与 `EpisodeIdempotencyConflict` 的 HTTP `message` 使用固定英文文案（领域异常本身无 payload）。

### 6.2 `GET /health`

- **响应**：`200 { "status": "ok" }`
- **行为**：不访问数据库，仅表示进程存活。

### 6.3 `GET /ready`

- **响应（就绪）**：`200 { "status": "ready" }`
- **响应（未就绪）**：`503 { "status": "not_ready", "reason": "<stable_code>" }`

`reason` 必须使用稳定机器码，**不得**暴露 `str(exception)` 等内部消息：

| reason | 条件 |
|---|---|
| `runtime_not_started` | `AppRuntime` 未 `startup()` |
| `database_unavailable` | PostgreSQL 连接池不可用或 `SELECT 1` 失败 |
| `memory_disabled` | `modules.memory_enabled` 为 `False` |

检查项：`AppRuntime` 已 `startup()`、memory 已启用、PostgreSQL 连接池可用（`SELECT 1`）。

## 7. 数据流

```text
Client
  → POST /v1/tenants/{tenant_id}/episodes
  → FastAPI 校验 path/body tenant_id 一致性、X-Correlation-Id 格式
  → Mapper: RecordEpisodeRequest → RecordEpisodeCommand
  → runtime.record_episode_handler().handle(command)
      → authorize(action="record_episode")
      → build Episode + append + outbox.publish (if created) + commit
  → Mapper: RecordEpisodeResult → HTTP response
  → 201/200 + episode_id
```

写入成功后，Outbox 行由已有事务保证；Relay 仍通过独立调用 `relay_outbox_once()` 或未来后台进程处理，不在本 HTTP 进程内自动启动。

## 8. 配置

```python
class HttpSettings:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8080
```

环境变量：`ENGRAMMESH__HTTP__HOST`, `ENGRAMMESH__HTTP__PORT`, `ENGRAMMESH__HTTP__ENABLED`

启动命令：

```bash
ENGRAMMESH__ENVIRONMENT=development \
ENGRAMMESH__POSTGRES__DSN=postgresql://engrammesh:engrammesh@localhost:5432/engrammesh \
ENGRAMMESH__TEMPORAL__NAMESPACE=demo \
ENGRAMMESH__TEMPORAL__TASK_QUEUE=demo \
uv run --python 3.14 --project services \
  python -m engrammesh.bootstrap.server
```

Lifespan 通过 `create_app(runtime, lifespan=lifespan)` 传入 `FastAPI(lifespan=...)`，在 `server.py` 中定义 `startup`/`shutdown` 钩子。

## 9. 鉴权

v1 继续使用 `EnvironmentGatedMemoryAuthorization`：

| Environment | `authorize(...)` |
|---|---|
| `development` | 全部允许 |
| `test` | 全部允许 |
| `staging` | 全部拒绝 → HTTP 403 |
| `production` | 全部拒绝 → HTTP 403 |

OIDC 切片落地后，HTTP 层将增加 JWT 中间件并将 actor/tenant 注入 mapper，不改动 `RecordEpisodeHandler` 签名。

## 10. 测试策略

| 层级 | 范围 | 标记 |
|---|---|---|
| 单元 | mapper 往返、tenant_id 不一致、错误信封、readiness reason 码 | 默认 |
| 集成 | `httpx` + `create_app(runtime)`（mock 或真实 postgres） | 默认 |
| 集成（postgres） | 端到端 POST → 验证 episode 与 outbox 行 | `@pytest.mark.postgres` |
| 契约 | request body 符合 `record-episode-request.schema.json`；**不含** `tenant_id` 的 episode 事件 schema 不被误用 | 默认 |

**必须覆盖的场景：**

1. 首次写入 → `201 created=true`
2. 完全相同请求重放 → `200 created=false`，相同 `episode_id`
3. 相同 `idempotency_key` 但字段不一致 → `409`
4. `environment=staging` → `403`
5. path `tenant_id` 与 body 不一致 → `422`
6. 非法 `X-Correlation-Id`（非 UUID）→ `422`
7. `/ready` runtime 未启动 → `503 reason=runtime_not_started`
8. `memory_enabled=False` 时 POST → `503 service_unavailable`

## 11. 文档变更

- 更新 `services/README.md` 与 `services/README.zh-CN.md`：HTTP API 章节、启动命令、错误码表、staging/production 写入限制说明。
- 更新 `CHANGELOG.md` Unreleased 节。

## 12. 验收标准

1. `uv run --python 3.14 --project services pytest services/tests -q` 全部通过。
2. `ruff check` 与 `mypy services/src` 无新增错误。
3. 本地启动 HTTP 服务后，可通过 `curl` 完成 episode 写入与幂等重放。
4. PostgreSQL 集成测试验证 outbox 事件与 episode 同事务写入；outbox payload.scope **无** `tenant_id`。
5. 架构依赖测试（domain/kernel）无回归；HTTP 层不违反模块内向依赖规则。

## 13. 后续切片顺序

```text
① Episode Ingest HTTP API          ✅
② Inbox 消费者 + episode-recorded 处理器   ✅
③ Episode 读取 API                 ✅（见 RFC 2026-07-31-episode-read-http-api.md）
④ OIDC 租户上下文                 ✅
⑤ Temporal Runtime 适配器         ✅
```

## 14. 风险与缓解

| 风险 | 缓解 |
|---|---|
| HTTP scope 与事件 scope 字段不一致 | §5.2 明确 mapper 边界；契约测试分别覆盖两种 schema |
| FastAPI 引入新的第三方依赖 | 限制在 bootstrap/http，architecture 测试不覆盖此层 |
| staging/production 默认拒绝所有写入 | 文档醒目说明；OIDC 切片前仅 dev/test 环境可用 |
| `/ready` 泄漏内部异常 | 使用稳定 `reason` 码表（§6.3） |
| HTTP 与 Relay 分进程导致演示链路多步 | README 提供 compose 示例脚本；Inbox 切片后简化 |
