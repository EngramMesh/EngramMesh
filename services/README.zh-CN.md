# EngramMesh 服务架构脚手架

简体中文 | [English](README.md)

## 目的与明确的非目标

本目录包含经过测试的 EngramMesh Python 3.14 服务架构脚手架，以及一个经过测试的 Episode 摄取应用切片和一个经过测试的持久化执行运行时切片。它定义了不可变的共享标识符与事件元数据、记忆模块和持久化运行时的公共契约、依赖规则、类型化进程配置、从设置装配 PostgreSQL 记忆 Handler 与运行时编排的组合根、带版本的 JSON Schema 事件契约，以及仅用于测试与开发的事务型内存 Adapter。

它**不**包含执行 HTTP API、PostgreSQL 执行快照存储、外部事件分发器、依赖注入框架、模型或工具集成、投影流水线或可部署产品功能。最小 HTTP 控制 API 已暴露 Episode 摄取、Episode 读取、健康探针，以及可选的 OIDC Bearer JWT 鉴权；生产加固仍属后续工作。内存 Adapter 仅在单个进程内保存状态，并不持久化。当 `temporal.enabled=true` 时，独立的 Temporal Worker 入口用于持久化工作流执行。测试通过只能证明本文所述应用契约与架构契约成立，并不表示已经存在可部署的运行时。

## 模块树

```text
services/
├── src/engrammesh/
│   ├── bootstrap/
│   │   ├── composition.py    # AppRuntime 组合根
│   │   ├── http/             # FastAPI 控制 API（Episode 摄取、探针）
│   │   ├── infrastructure.py # 默认时钟、标识符与授权 Port
│   │   ├── server.py         # uvicorn 入口
│   │   ├── settings.py       # 类型化、不可变的配置边界
│   │   └── worker.py         # Temporal Worker 入口
│   ├── modules/
│   │   ├── memory/
│   │   │   ├── adapters/     # 内存与 PostgreSQL 事务 Adapter
│   │   │   │   ├── in_memory/  # 进程内测试/开发 Adapter
│   │   │   │   └── postgres/   # 持久化 Episode/Outbox Adapter（psycopg）
│   │   │   ├── application/  # 与框架无关的 Episode 摄取编排
│   │   │   ├── domain/       # 纯认知记忆值对象与不变量
│   │   │   ├── ports.py      # 与实现无关的边界
│   │   │   └── public.py     # 跨模块公共契约
│   │   └── runtime/
│   │       ├── adapters/     # 内存与 Temporal 编排 Adapter
│   │       │   ├── in_memory/  # ExecutionIndex + InMemoryOrchestratorPort
│   │       │   └── temporal/   # TemporalOrchestratorPort、工作流、活动
│   │       ├── application/  # 与框架无关的执行编排
│   │       ├── domain/       # 纯持久化执行值对象与状态转换
│   │       ├── ports.py      # 与实现无关的边界
│   │       └── public.py     # 跨模块公共契约
│   └── shared/kernel/        # 共享类型化 ID 与事件信封
└── tests/
    ├── architecture/         # 依赖策略测试
    ├── contract/             # 公共契约、Schema 与可复用 Adapter 契约
    ├── integration/          # 应用与具体 Adapter 的集成测试
    └── unit/                 # 不变量、应用与 Adapter 单元测试

packages/contracts/jsonschema/
├── events/v1/               # 通用事件信封
├── memory/v1/               # 记忆事件载荷
└── runtime/v1/              # 运行时事件载荷
```

## 依赖方向

共享内核只能依赖 Python 标准库。模块领域层可以依赖标准库、共享内核、自身领域层，以及其他模块严格限定的 `public.py` 契约。它不得导入其他模块的内部实现、自身的公共门面、Adapter 或第三方包。Port 与公共门面向内指向领域契约。`bootstrap/settings.py` 是当前脚手架中唯一使用 Pydantic Settings 的边界；领域代码保持与框架无关。

```text
bootstrap/配置              模块公共契约
      |                           |
      v                           v
bootstrap/composition.py -> 应用服务 -> Port -> 领域层
                            |
                            v
                          共享内核
```

未来 Adapter 将实现 Port 并向内依赖。领域代码和应用代码绝不能向外依赖具体 Adapter。

## 权威状态边界

- PostgreSQL 是持久化记忆事实、版本化记录、追加事件和持久化结构快照的权威来源。本切片中的 PostgreSQL Episode Adapter 实现了 Episode 摄取持久化；更广泛的记忆表面与行级安全（RLS）策略仍属后续工作。
- Temporal Event History 将作为执行生命周期、定时器、重试和持久化工作流进度的权威来源。
- 对象存储将作为由不可变引用寻址的大型内容的权威来源。
- 向量索引、图存储、缓存、搜索索引和遥测是可重建投影或运行信号，绝不是主要权威来源。
- 通用契约与 Schema 定义稳定的形状和不变量。内存 Adapter 仅在单个进程内保留已提交的 Episode 与 Outbox 状态；它不提供持久化权威来源、外部分发或投影。

## 第三方 Adapter 策略

PostgreSQL 驱动、Temporal SDK、模型提供方、工具协议、对象存储、向量数据库、图数据库和遥测导出器必须在现有 Port 或经过单独评审的 Port 后实现。供应商类型、客户端、异常和重试策略不得泄漏到领域模型或模块公共契约中。Adapter 负责与稳定的 EngramMesh 类型相互转换，强制传递租户与授权上下文，并接受确定性契约测试。增加提供方依赖库还必须有具体的 Adapter 用例，不得提前推测性引入。

## Episode 摄取切片

`RecordEpisodeHandler` 是一个与框架无关的应用服务。它先完成授权，再使用注入的时钟与标识符 Port，按内容引用记录一个不可变 `Episode`。具体持久化实现包括 `InMemoryMemoryUnitOfWorkFactory`（进程内）和 `PostgresMemoryUnitOfWorkFactory`（持久化 PostgreSQL）。PostgreSQL 类型应从 `engrammesh.modules.memory.adapters.postgres` 导入，而非顶层 `engrammesh.modules.memory.adapters` 包（该包仅导出内存 Adapter）。

本切片明确不包含依赖注入框架装配、Temporal、对象上传、Claim 提取、检索、纠正与删除、投影，以及外部 Outbox 分发。HTTP 传输由 `bootstrap/http/` 单独提供；内存 Adapter 不提供跨进程持久性或投递保证。

## 应用流程

```text
RecordEpisodeCommand
  -> authorize(action="record_episode", actor, exact scope, sensitivity)
  -> 使用注入的时间与 Memory ID 构造 Episode
  -> 创建 MemoryUnitOfWork
      -> EpisodeStore.append
      -> 若为新建：OutboxPort.publish(memory.episode-recorded)
      -> commit
  -> RecordEpisodeResult(episode_id, created)
```

授权在事务开启前完成。无效命令值、领域值和 Adapter 错误会原样向上传播，因为与传输层有关的错误转换不属于本切片。Handler 会拒绝无时区的时钟值，并在构造 Episode 或事件前把时钟时间和命令中的 `observed_at` 都规范化为 UTC。

## 幂等与事务语义

幂等范围是 `(tenant_id, idempotency_key)`。第一次追加返回 `created=True`。只有在 Scope、Actor、来源类型、内容引用、观察时间、内容哈希、敏感级别、保留类别和同意依据全部匹配时，冲突才属于精确重放；生成的 Episode ID 和 `ingested_at` 不参与比较。`correlation_id` 是 Outbox 追踪元数据而非 Episode 定义的不可变字段，因此也不参与比较。精确重放返回原始 Episode ID 和 `created=False`，且不会暂存第二个事件；任一上述参与比较的 Episode 定义字段不同都会抛出不携带载荷的 `EpisodeIdempotencyConflict`，且不改变状态。不同租户可以复用同一键。

内存 Adapter 使用一个进程内锁串行化事务，并采用写时复制状态。成功的 `commit()` 会让新快照立即成为最终状态并全局可见；之后事务体抛出异常、被取消或退出上下文，都不会恢复旧状态。未调用 `commit()` 就退出时，仍会丢弃暂存的 Episode、幂等索引与 Outbox 变更。

对于 `memory.episode-recorded`，Outbox 发布要求聚合 Episode 在当前事务中可见（无论是此前已提交还是本次新暂存），并要求信封租户与 Episode 租户一致。未知或跨租户的 Episode 聚合会被拒绝；其他事件类型不受这条 Episode 关联规则约束。所有接受的带时区时间都会以规范 UTC 序列化。这些行为是用于本地测试/开发的原子模型，不是生产级并发、持久化或外部投递模型。

## PostgreSQL Episode Adapter

`PostgresMemoryDatabase` 与 `PostgresMemoryUnitOfWorkFactory` 提供事务作用域内的 Episode 存储、不可用的 Claim 存储和 Outbox Port，由带版本 SQL 迁移与 psycopg3 异步连接池支撑。仅 `engrammesh.modules.memory.adapters.postgres` 可导入 `psycopg`；领域、应用与 Port 模块保持与提供方无关。

```python
from engrammesh.modules.memory.adapters.postgres import (
    PostgresMemoryDatabase,
    PostgresMemoryUnitOfWorkFactory,
)
```

`EPISODE_ADAPTER_CONTRACTS` 中的可移植 Episode 断言通过 PostgreSQL Harness 绑定，不修改共享断言主体。PostgreSQL 能力契约（`POSTGRES_EPISODE_CAPABILITY_CONTRACTS`）单独描述不可用的 Claim 操作与被拒绝的非 `None` 流游标。

租户隔离通过 SQL 谓词强制（每次读写均带 `tenant_id`）。PostgreSQL 行级安全（RLS）策略推迟到后续生产加固切片。`PostgresSettings` 通过 `AppSettings` 读取，并在 memory 启用时由 `bootstrap/composition.py` 装配。

### 本地 PostgreSQL 测试

设置 DSN 后运行带 `postgres` 标记的测试。未设置 `ENGRAMMESH__POSTGRES__DSN` 时，`@pytest.mark.postgres` 测试会跳过。共享同一数据库的测试通过 `postgres_serial` xdist 组串行执行：

```bash
export ENGRAMMESH__POSTGRES__DSN=postgresql://engrammesh:engrammesh@localhost:5432/engrammesh
ENGRAMMESH__POSTGRES__DSN=postgresql://engrammesh:engrammesh@localhost:5432/engrammesh \
  uv run --python 3.14 --project services pytest services/tests -m postgres -q
```

使用相同 DSN 运行完整 services 套件（postgres 与非 postgres）：

```bash
ENGRAMMESH__POSTGRES__DSN=postgresql://engrammesh:engrammesh@localhost:5432/engrammesh \
  uv run --python 3.14 --project services pytest services/tests -q
```

## 组合根

`bootstrap/composition.py` 是官方组合根。它读取类型化 `AppSettings`，在启动时打开 PostgreSQL 连接池，并返回装配了基础设施 Port 的缓存 `RecordEpisodeHandler`。只有 bootstrap 可以导入 `engrammesh.modules.memory.adapters.postgres` 并装配应用服务。

```python
from engrammesh.bootstrap.composition import create_runtime, load_settings
```

`load_settings()` 是 `AppSettings()` 的薄封装，提供单一配置入口。`create_runtime()` 可接受可选 settings，默认调用 `load_settings()`；在显式调用生命周期方法或使用 async 上下文管理器之前不会执行 `startup()`。

```bash
export ENGRAMMESH__ENVIRONMENT=test
export ENGRAMMESH__POSTGRES__DSN=postgresql://engrammesh:engrammesh@localhost:5432/engrammesh
export ENGRAMMESH__TEMPORAL__NAMESPACE=demo
export ENGRAMMESH__TEMPORAL__TASK_QUEUE=demo
PYTHONPATH=services/src PYTHONDONTWRITEBYTECODE=1 \
  uv run --python 3.14 --project services python - <<'PY'
import asyncio
from datetime import UTC, datetime
from uuid import UUID

from engrammesh.bootstrap.composition import create_runtime, load_settings
from engrammesh.modules.memory.application.contracts import RecordEpisodeCommand
from engrammesh.modules.memory.domain.model import (
    MemoryScope,
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.shared.kernel.ids import (
    ArtifactId,
    CorrelationId,
    SubjectId,
    TenantId,
)


async def main() -> None:
    async with create_runtime(load_settings()) as runtime:
        handler = runtime.record_episode_handler()
        command = RecordEpisodeCommand(
            correlation_id=CorrelationId(UUID(int=3)),
            actor_id=SubjectId(UUID(int=4)),
            scope=MemoryScope(
                tenant_id=TenantId(UUID(int=5)),
                subject_id=SubjectId(UUID(int=6)),
                workspace_id="demo",
            ),
            source_type=SourceType.USER,
            content_ref=ArtifactId(UUID(int=7)),
            observed_at=datetime(2026, 7, 27, 9, 0, tzinfo=UTC),
            content_hash="sha256:demo",
            idempotency_key="demo-composed-episode",
            sensitivity=Sensitivity.CONFIDENTIAL,
            retention_class=RetentionClass.STANDARD,
            consent_basis="user_request",
        )
        first = await handler.handle(command)
        replay = await handler.handle(command)
        print(f"first_created={first.created} replay_created={replay.created}")
        print(f"same_id={first.episode_id == replay.episode_id}")


asyncio.run(main())
PY
```

当 `modules.memory_enabled` 为 `False` 时，`record_episode_handler()` 抛出 code 为 `memory_disabled` 的 `ConfigurationError`。当 memory 已启用但 `startup()` 尚未完成时，抛出消息为 `application runtime is not started` 的 `RuntimeError`。

## 运行时执行切片

运行时模块通过 `AppRuntime` 装配的三个应用 Handler 提供持久化多 Agent 执行编排：

| Handler | 命令 / 查询 | 动作 |
|---------|------------|------|
| `StartExecutionHandler` | `StartExecutionCommand` | 授权 + 启动执行 |
| `GetExecutionSnapshotHandler` | `GetExecutionSnapshotQuery` | 授权 + 读取快照 |
| `CancelExecutionHandler` | `CancelExecutionCommand` | 授权 + 取消执行 |

访问器：`start_execution_handler()`、`get_execution_snapshot_handler()`、
`cancel_execution_handler()`。当 `modules.runtime_enabled` 为 `False` 时，均抛出
code 为 `runtime_disabled` 的 `ConfigurationError`。

### ExecutionIndex 与工作流标识

`AppRuntime` 在进程生命周期内拥有**单例** `InMemoryRuntimeDatabase`（别名
`ExecutionIndex`）。索引映射 `(tenant_id, idempotency_key) → execution_id`，
并在内存编排器激活时存储完整快照。

**工作流 ID 方案：** `{tenant_id}:{execution_id}`。`InMemoryOrchestratorPort`
与 `TemporalOrchestratorPort` 均使用该格式。`get_snapshot` 通过租户与执行 id
解析工作流，无需反向索引。启动幂等性在 `start_workflow` 之前使用
`ExecutionIndex`；重放时描述已有工作流而非创建新工作流。

`StartExecutionHandler` 通过比较返回快照的 `execution_id` 与新生成的 id 推断
`created`：首次调用 → `created=True`；精确幂等重放返回已存储 id →
`created=False`。

### 启用矩阵

| `runtime_enabled` | `temporal.enabled` | 编排器 | 说明 |
|-------------------|-------------------|--------|------|
| `false` | 任意 | 无 | Handler 抛出 `runtime_disabled` |
| `true` | `false` | `InMemoryOrchestratorPort` | 默认；CI 与本地开发 |
| `true` | `true` | `TemporalOrchestratorPort` | 需要运行 Temporal Worker |

Memory 与 Runtime 启动相互独立；memory 禁用时仍可使用运行时 Handler。

### 内存 vs Temporal

| 关注点 | `temporal.enabled=false` | `temporal.enabled=true` |
|--------|--------------------------|-------------------------|
| 快照权威 | `ExecutionIndex`（进程内） | Temporal 工作流查询 `current_snapshot` |
| 持久性 | 无（进程内） | Temporal Event History |
| Worker | 不需要 | `bootstrap/worker.py` 在配置的任务队列上运行 |
| SDK 边界 | 不适用 | `temporalio` 仅限 `adapters/temporal/` 与 `worker.py` |

`InMemoryOrchestratorPort` 实现完整 `OrchestratorPort` 契约，包括幂等指纹、
租户作用域读取与取消状态转换。`TemporalOrchestratorPort` 共享同一
`ExecutionIndex` 处理启动幂等，并将生命周期委托给 `ExecutionLifecycleWorkflow`
及桩活动（`advance_to_planning`、`advance_to_running`、`advance_to_succeeded`）。
SDK 错误包装为 `OrchestrationUnavailable`。

可移植编排器断言位于 `ORCHESTRATOR_PORT_CONTRACTS`
（`tests/contract/orchestrator_adapter_contract.py`）；内存 Adapter 率先绑定。

### 启动 Temporal Worker

Worker 与 HTTP 服务分离运行。需要 `temporal.enabled=true` 且 Temporal 服务可达：

```bash
export ENGRAMMESH__TEMPORAL__ENABLED=true
export ENGRAMMESH__TEMPORAL__NAMESPACE=demo
export ENGRAMMESH__TEMPORAL__TASK_QUEUE=demo
uv run --python 3.14 --project services \
  python -m engrammesh.bootstrap.worker
```

`worker.py` 在配置的任务队列上注册 `ExecutionLifecycleWorkflow` 与桩活动，
并在 `SIGINT`/`SIGTERM` 时优雅关闭。

### Temporal 测试

默认 pytest 排除带 `temporal` 标记的测试：

```toml
# services/pyproject.toml
addopts = "-m 'not temporal'"
```

显式运行 Temporal 集成测试：

```bash
uv run --python 3.14 --project services pytest services/tests -m temporal -q
```

Temporal 测试使用 `WorkflowEnvironment` 时间跳过，验证工作流完成、启动幂等重放、
取消与 Worker 重启恢复。

### 运行时非目标

本切片明确不包含：

- 执行 HTTP API（Slice 3 — 后续 ④a）
- PostgreSQL 执行快照存储与运行时 Outbox 事件（Slice 4 — 后续 ④b）
- LangGraph、PlannerPort、AgentEnginePort、完整 Plan DAG 执行
- Claim 提取（Phase 2）
- OIDC 运行时授权（推迟至执行 HTTP 工作）

详见 `docs/rfcs/2026-07-31-temporal-runtime-adapter.md` 与
`docs/superpowers/specs/2026-07-31-temporal-runtime-adapter-design.md`。

## Outbox Relay

`RelayOutboxEventsHandler` 轮询 `memory_outbox_events` 中未发布的行，通过 `OutboxEventPublisher` 分发，并仅在批次内所有 `publish` 调用成功后设置 `published_at`。`AppRuntime` 通过 `relay_outbox_handler()`、`relay_outbox_once()` 与 `run_outbox_relay_loop()` 装配该中继。

**命名：** `OutboxPort.publish`（Episode 摄取事务内的写入）与 `OutboxEventPublisher.publish`（store 事务外的中继分发）是不同职责，文档与代码评审必须明确区分。

v1 假定**每个数据库仅有一个活跃中继 Worker**（无 `SKIP LOCKED`）。行按全局顺序 `occurred_at ASC, event_id ASC` 获取。投递为**至少一次**：若在成功 `publish` 之后、`mark_published` 之前进程崩溃，重试可能再次分发同一事件；下游消费者须按 `event_id` 去重（见 [Inbox 消费者](#inbox-消费者)）。任一 `publish` 失败时，Handler 立即重新抛出，不调用 `mark_published`；调用方不会收到 `RelayOutboxResult`。失败前已成功 dispatch 的事件可能已投递，但 `published_at` 仍为 NULL。

```python
async with create_runtime(load_settings()) as runtime:
    await runtime.record_episode_handler().handle(command)
    result = await runtime.relay_outbox_once()
    print(result.published, runtime.logging_outbox_event_publisher.published)
```

`relay_outbox_handler()` 在 memory 禁用时抛出 code 为 `memory_disabled` 的 `ConfigurationError`（先于中继相关错误检查），在 `outbox_relay.enabled` 为 `False` 时抛出 `outbox_relay_disabled`，在运行时未启动时抛出 `RuntimeError`。默认 `LoggingOutboxEventPublisher` 在进程内记录已分发事件供测试使用；生产消息中间件实现同一 Port，无需修改 Handler。

## Inbox 消费者

当 `inbox.enabled` 为 `True`（默认）时，中继分发经 `InboxOutboxEventPublisher` 流转：先执行 Inbox 处理，再调用日志委托。`ProcessInboxEventHandler` 将受支持的事件路由到可插拔 Processor；v1 注册 `EpisodeRecordedProcessor` 对 `memory.episode-recorded` 做结构不变量校验（无投影副作用）。

```text
RelayOutboxEventsHandler
  → InboxOutboxEventPublisher.publish(event)
      → ProcessInboxEventHandler.handle(event)
          → 按 event_type 选择 InboxEventProcessor
          → InboxStore.try_record(event_id, ...)
          → EpisodeRecordedProcessor.process(event)
          → 失败时：InboxStore.remove_record(event_id)
      → LoggingOutboxEventPublisher.publish(event)   # 仅测试可见性
  → OutboxRelayStore.mark_published(...)
```

**委托与 Inbox 权威：** `InboxOutboxEventPublisher` 在 Inbox 处理后始终调用日志委托，包括 Handler 返回 `skipped=True`（重复或不支持的事件）时。测试中断言分发可见性请用 `logging_outbox_event_publisher.published`；已处理权威请查 `memory_inbox_events` 行数。`LoggingOutboxEventPublisher.published` **不是**去重权威来源。

| 结果 | `processed` | `skipped` | Inbox 行 |
|------|-------------|-----------|----------|
| 不支持的 `event_type` | `False` | `True` | 不写入 |
| 重复 `event_id` | `False` | `True` | 不变 |
| 新事件处理成功 | `True` | `False` | 已写入 |

`try_record` 之后 Processor 失败会调用 `remove_record` 并重新抛出，中继不会 `mark_published`，从而可重试。不支持的事件类型跳过且不写 Inbox。

迁移 `003_inbox_events.sql` 创建 `memory_inbox_events`，主键为 `event_id uuid`。**v1 去重键仅为 `event_id`**（每库全局、单消费者）。`consumer_name` 用于审计与未来多消费者迁移，不参与主键；若多个消费者处理同一 `event_id`，需迁移为复合主键。

### 配置

```python
class InboxSettings:
    enabled: bool = True
    consumer_name: str = "episode-recorded-v1"
```

| 环境变量 | 默认值 |
|---------|--------|
| `ENGRAMMESH__INBOX__ENABLED` | `true` |
| `ENGRAMMESH__INBOX__CONSUMER_NAME` | `episode-recorded-v1` |

当 `inbox.enabled=False` 时，`AppRuntime` 仅使用 `LoggingOutboxEventPublisher`，行为与 Inbox 引入前的中继路径一致（不写 Inbox 表）。这是未应用迁移 `003` 或需回归验证时的回滚开关。

```python
async with create_runtime(load_settings()) as runtime:
    await runtime.record_episode_handler().handle(command)
    await runtime.relay_outbox_once()
    # 分发可见性（可能含重投）：
    runtime.logging_outbox_event_publisher.published
    # 已处理权威 — 查询 memory_inbox_events
```

`outbox_event_publisher` 返回已装配的发布者（`InboxOutboxEventPublisher` 或 `LoggingOutboxEventPublisher`）。`logging_outbox_event_publisher` 始终暴露内部委托。需要 Inbox 处理时通过 `process_inbox_handler()` 构建 Handler。

### 授权

Episode HTTP 路由通过 `create_memory_authorization()` 在组合时按 `oidc.enabled` 选择两种授权策略之一。

#### OIDC 关闭时（`oidc.enabled=false`，默认）

`EnvironmentGatedMemoryAuthorization` 按 `ENGRAMMESH__ENVIRONMENT` 门控授权。不要求 Bearer 令牌。`actor_id` 来自请求体（`POST`）或查询参数（`GET`）。

| `Environment` | `authorize(...)` 结果 |
|---------------|----------------------|
| `development` | 所有请求返回 `True` |
| `test`        | 所有请求返回 `True` |
| `staging`     | 所有请求返回 `False` |
| `production`  | 所有请求返回 `False` |

授权被拒绝时抛出 `EpisodeAuthorizationDenied` 或 `EpisodeReadAuthorizationDenied`。在 HTTP API 上，`staging` 与 `production` 因此返回 **403**，`error.code` 为 `episode_authorization_denied` 或 `episode_read_authorization_denied`；未启用 OIDC 的本地练习请使用 `development` 或 `test`。

#### OIDC 鉴权（`oidc.enabled=true`）

启用 OIDC 后，`POST` 与 `GET` Episode 路由需要有效的 `Authorization: Bearer <jwt>` 请求头。`/health` 与 `/ready` 仍无需鉴权。JWT 校验与主体绑定位于 `bootstrap/auth/`；应用 Handler 签名不变。

`TenantScopedMemoryAuthorization` 取代环境门控：JWT 中的 `actor_id` 须与命令/查询中的 `actor_id` 一致，JWT 中的 `tenant_id` 须与请求 scope 租户一致。路径 `{tenant_id}` 须与 JWT 租户声明一致；不匹配时在 Handler 执行前返回 **403** `tenant_access_denied`。

**校验器选择**（`create_token_verifier`）：

| 条件 | 校验器 |
|------|--------|
| `environment` 为 `development` 或 `test`，且设置了 `dev_signing_key` | `StaticDevTokenVerifier`（HS256） |
| 设置了 `jwks_uri` | `JwksTokenVerifier`（经 JWKS 的 RS256 / ES256 / EdDSA） |
| 启用 OIDC 但以上均不满足 | 启动时 `ConfigurationError`（`oidc_misconfigured`） |

`dev_signing_key` **仅用于开发与测试**。生产环境在启用 OIDC 时拒绝该配置（`oidc_dev_key_forbidden`），并要求非空的 `issuer` 与 `jwks_uri`。

**JWT 声明要求**（默认名称可通过 `actor_claim` / `tenant_claim` 配置）：

| 声明 | 默认名称 | 要求 |
|------|----------|------|
| Actor | `sub` | 必填；须为 UUID 字符串 |
| Tenant | `tenant_id` | 必填；须为 UUID 字符串 |
| 过期 | `exp` | 必填 |
| 签发者 | `iss` | 须与配置的 `issuer` 一致 |
| 受众 | `aud` | 仅当配置了 `audience` 时校验 |

已鉴权时 `actor_id` 取自 JWT。在请求体或查询中提供 `actor_id` 返回 **422** `actor_id_not_allowed`。OIDC 关闭时省略 `actor_id` 返回 **422** `actor_id_required`。

**配置**（`OidcSettings`）：

| 字段 | 默认值 | 环境变量 |
|------|--------|----------|
| `enabled` | `false` | `ENGRAMMESH__OIDC__ENABLED` |
| `issuer` | `""` | `ENGRAMMESH__OIDC__ISSUER` |
| `jwks_uri` | `""` | `ENGRAMMESH__OIDC__JWKS_URI` |
| `audience` | `null` | `ENGRAMMESH__OIDC__AUDIENCE` |
| `actor_claim` | `sub` | `ENGRAMMESH__OIDC__ACTOR_CLAIM` |
| `tenant_claim` | `tenant_id` | `ENGRAMMESH__OIDC__TENANT_CLAIM` |
| `dev_signing_key` | `null` | `ENGRAMMESH__OIDC__DEV_SIGNING_KEY` |

**Staging 集成测试**可在不修改 Handler 的情况下注入校验器：

```python
from engrammesh.bootstrap.http.app import create_app

app = create_app(
    runtime,
    lifespan=lifespan,
    token_verifier=my_test_verifier,  # 覆盖 runtime.token_verifier()
)
```

**OIDC 错误码**（除下文摄取/读取错误码外）：

| 状态码 | `error.code` | 触发条件 |
|--------|--------------|----------|
| `401` | `authentication_required` | 缺少或空白的 `Authorization` 请求头 |
| `401` | `invalid_token` | Bearer 前缀格式错误、JWT 无效或校验失败 |
| `403` | `tenant_access_denied` | JWT 租户声明与路径 `{tenant_id}` 不一致 |
| `422` | `actor_id_not_allowed` | 启用 OIDC 时在 body 或 query 中提供了 `actor_id` |
| `422` | `actor_id_required` | 关闭 OIDC 时缺少 `actor_id` |

## Episode 摄取 HTTP API

`bootstrap/http/` 暴露首个 Control API 切片：通过 REST 调用 `RecordEpisodeCommand`，经 `create_app(runtime, lifespan=lifespan)` 与 `AppRuntime.record_episode_handler()` 装配。FastAPI 与 uvicorn 仅出现在 bootstrap；领域与应用模块保持与框架无关。

```python
from engrammesh.bootstrap.http.app import create_app
```

### 端点

| 方法 | 路径 | 成功状态码 | 说明 |
|------|------|-----------|------|
| `GET` | `/health` | `200` | 存活探针；不访问数据库 |
| `GET` | `/ready` | `200` 或 `503` | 就绪探针；检查运行时启动、memory 启用与 PostgreSQL |
| `POST` | `/v1/tenants/{tenant_id}/episodes` | `201` 或 `200` | 记录一条 Episode；新建为 `201`，精确幂等重放为 `200` |
| `GET` | `/v1/tenants/{tenant_id}/episodes/{episode_id}` | `200` / `403` / `404` / `422` / `503` | 按精确 scope 读取单条 Episode |
| `GET` | `/v1/tenants/{tenant_id}/episodes` | `200` / `403` / `422` / `503` | 列出 Episode（keyset 游标分页） |

`POST` 接受可选请求头 `X-Correlation-Id`（UUID）。缺省时服务端生成新 correlation ID；非 UUID 格式返回 **422**。

路径 `tenant_id` 必须与 body `scope.tenant_id` 一致；不一致返回 **422**。

**成功响应体：**

| 端点 | 状态码 | 响应体 |
|------|--------|--------|
| `GET /health` | `200` | `{ "status": "ok" }` |
| `GET /ready` | `200` | `{ "status": "ready" }` |
| `POST .../episodes` | `201` | `{ "episode_id": "<uuid>", "created": true }` |
| `POST .../episodes` | `200` | `{ "episode_id": "<uuid>", "created": false }`（幂等重放） |

### HTTP scope 与事件 scope 差异

HTTP 请求体使用独立传输 Schema（`record-episode-request.schema.json`），**不得**复用 Outbox 事件 payload Schema。

| 层面 | tenant 位置 | `scope` 字段 |
|------|------------|--------------|
| HTTP 请求体 | `scope.tenant_id`（必填）+ path `tenant_id`（须一致） | `tenant_id`, `subject_id`, `workspace_id?`, `agent_id?` |
| Outbox 事件 envelope | 信封层 `tenant_id` | — |
| Outbox 事件 `payload.scope` | **不含** `tenant_id` | `subject_id`, `workspace_id?`, `agent_id?` |

path/body 双写 `tenant_id` 用于网关路由、审计与请求校验。`RecordEpisodeHandler` 发布事件时，`payload.scope` 仍不包含 `tenant_id`。

### 错误响应

Episode 摄取错误使用统一信封：

```json
{
  "error": {
    "code": "<machine_readable_code>",
    "message": "<human_readable_message>",
    "details": []
  }
}
```

| 状态码 | `error.code` | 触发条件 |
|--------|--------------|----------|
| `401` | `authentication_required` | 启用 OIDC；缺少 `Authorization` 请求头 |
| `401` | `invalid_token` | 启用 OIDC；Bearer JWT 校验失败 |
| `403` | `tenant_access_denied` | 启用 OIDC；JWT 租户 ≠ 路径 `{tenant_id}` |
| `403` | `episode_authorization_denied` | `EpisodeAuthorizationDenied`（含 OIDC 关闭时的 `staging` / `production`） |
| `409` | `episode_idempotency_conflict` | 相同 `(tenant_id, idempotency_key)` 但 Episode 定义字段不同 |
| `422` | `actor_id_not_allowed` | 启用 OIDC；body 中提供了 `actor_id` |
| `422` | `actor_id_required` | 关闭 OIDC；body 中缺少 `actor_id` |
| `422` | `validation_error` | Pydantic 校验失败、path/body `tenant_id` 不一致、非法 `X-Correlation-Id` |
| `503` | `service_unavailable` | `ConfigurationError`（如 `memory_disabled`、`http_disabled`） |
| `500` | `internal_error` | 未预期异常（响应不泄漏堆栈） |

### `/ready` reason 码

未就绪时 `GET /ready` 返回 **503**：

```json
{ "status": "not_ready", "reason": "<stable_code>" }
```

| `reason` | 条件 |
|----------|------|
| `runtime_not_started` | `AppRuntime.startup()` 尚未完成 |
| `database_unavailable` | PostgreSQL 连接池不可用或 `SELECT 1` 失败 |
| `memory_disabled` | `modules.memory_enabled` 为 `False` |

`GET /ready` 使用上述 `not_ready` 体。Episode `POST` **不**调用 `check_ready()`；
`memory_disabled` 时 `POST` 返回 `error` 信封，`code` 为 `service_unavailable`（见错误表）。
若在 `AppRuntime.startup()` 完成前调用 `POST`，`record_episode_handler()` 抛出
`RuntimeError`，映射为 **500** `internal_error`。

### 启动 HTTP 服务

通过 `ENGRAMMESH__HTTP__HOST`、`ENGRAMMESH__HTTP__PORT`、`ENGRAMMESH__HTTP__ENABLED` 配置。授权写入请使用 `development` 或 `test`。

```bash
ENGRAMMESH__ENVIRONMENT=development \
ENGRAMMESH__POSTGRES__DSN=postgresql://engrammesh:engrammesh@localhost:5432/engrammesh \
ENGRAMMESH__TEMPORAL__NAMESPACE=demo \
ENGRAMMESH__TEMPORAL__TASK_QUEUE=demo \
uv run --python 3.14 --project services \
  python -m engrammesh.bootstrap.server
```

`server.py` 调用 `create_runtime`，定义 lifespan 的 `startup`/`shutdown`，并传入 `create_app`。HTTP 进程内不启动 Outbox relay；分发仍通过 `relay_outbox_once()` 或独立 Worker。

### `curl` 示例

```bash
curl -sS -X POST "http://127.0.0.1:8080/v1/tenants/53dad495-7915-439a-b03a-379452a1aa86/episodes" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: 02ffae84-2764-41f3-a22a-4d4652a7c139" \
  -d '{
    "actor_id": "3ba213e4-3367-4e7c-9635-bcbfbad505e6",
    "scope": {
      "tenant_id": "53dad495-7915-439a-b03a-379452a1aa86",
      "subject_id": "3d65c071-ac55-4847-a8f1-e3cb859d3c45",
      "workspace_id": "workspace-42"
    },
    "source_type": "user",
    "content_ref": "a2e57fc9-d07d-45dc-a647-76d195985d86",
    "observed_at": "2026-07-27T10:00:00+00:00",
    "content_hash": "sha256:88c7355c",
    "idempotency_key": "episode-42",
    "sensitivity": "confidential",
    "retention_class": "standard",
    "consent_basis": "user_request"
  }'
```

首次写入预期响应（`201`）：

```json
{ "episode_id": "<uuid>", "created": true }
```

使用相同请求重放可观察幂等响应（`200`）：

```json
{ "episode_id": "<相同-uuid>", "created": false }
```

## Episode 读取 HTTP API

`bootstrap/http/` 通过 `AppRuntime.get_episode_handler()` 与
`AppRuntime.list_episodes_handler()` 暴露按 scope 精确读取 Episode 的能力。
读取处理器使用 `read_episode` 授权（与摄取相同策略，见[授权](#授权)）。

### 读取查询参数

两个读取端点均需查询参数：

| 参数 | 必填 | 说明 |
|------|------|------|
| `subject_id` | 是 | 租户 scope 内的 subject UUID |
| `workspace_id` | 否 | 可选 workspace 收窄 |
| `agent_id` | 否 | 可选 agent 收窄 |
| `actor_id` | OIDC 关闭时必填；OIDC 开启时省略 | 授权主体；启用 OIDC 时取自 JWT |

列表端点额外接受：

| 参数 | 默认 | 说明 |
|------|------|------|
| `limit` | `50` | 页大小；最小 `1`，最大 `100` |
| `cursor` | 省略 | 上一页 `next_cursor` 返回的不透明游标；首页省略 |

### 读取成功响应

| 端点 | 状态码 | 响应体 |
|------|--------|--------|
| `GET .../episodes/{episode_id}` | `200` | 完整 `EpisodeResponse`（见 `episode-response.schema.json`） |
| `GET .../episodes` | `200` | `{ "items": [ /* EpisodeResponse */ ], "next_cursor": "..." \| null }` |

`EpisodeResponse` 包含 `episode_id`、`scope`（含 `tenant_id`）、`actor_id`、
`source_type`、`content_ref`、`observed_at`、`ingested_at`、`content_hash`、
`idempotency_key`、`sensitivity`、`retention_class`、`consent_basis`。
`content_ref` 为不透明引用；对象存储内容解析尚未实现。

### 读取错误响应

读取错误复用统一信封。摄取之外新增：

| 状态码 | `error.code` | 触发条件 |
|--------|--------------|----------|
| `401` | `authentication_required` | 启用 OIDC；缺少 `Authorization` 请求头 |
| `401` | `invalid_token` | 启用 OIDC；Bearer JWT 校验失败 |
| `403` | `tenant_access_denied` | 启用 OIDC；JWT 租户 ≠ 路径 `{tenant_id}` |
| `403` | `episode_read_authorization_denied` | `EpisodeReadAuthorizationDenied`（含 OIDC 关闭时的 `staging` / `production`） |
| `404` | `episode_not_found` | 未知 id、scope 不匹配或跨租户访问（不泄漏存在性） |
| `422` | `actor_id_not_allowed` | 启用 OIDC；query 中提供了 `actor_id` |
| `422` | `actor_id_required` | 关闭 OIDC；query 中缺少 `actor_id` |
| `422` | `invalid_episode_cursor` | 列表游标格式非法 |
| `422` | `validation_error` | UUID 非法、`limit` 超出范围（`1`–`100`） |
| `503` | `service_unavailable` | `ConfigurationError`（如 `memory_disabled`） |

错误租户、错误 `subject_id`、错误可选 scope 收窄或未知 `episode_id` 均返回 **404**
`episode_not_found`。跨租户存在性不得返回 **403**。

### `curl` 示例（记录 → 读取 → 列表）

先记录 Episode（同摄取示例），再读回：

```bash
EPISODE_ID="<post-响应中的-uuid>"

curl -sS "http://127.0.0.1:8080/v1/tenants/53dad495-7915-439a-b03a-379452a1aa86/episodes/${EPISODE_ID}" \
  "?subject_id=3d65c071-ac55-4847-a8f1-e3cb859d3c45" \
  "&workspace_id=workspace-42" \
  "&actor_id=3ba213e4-3367-4e7c-9635-bcbfbad505e6"

curl -sS "http://127.0.0.1:8080/v1/tenants/53dad495-7915-439a-b03a-379452a1aa86/episodes" \
  "?subject_id=3d65c071-ac55-4847-a8f1-e3cb859d3c45" \
  "&workspace_id=workspace-42" \
  "&actor_id=3ba213e4-3367-4e7c-9635-bcbfbad505e6" \
  "&limit=50"
```

当 `next_cursor` 非空时，在下一请求中以 `cursor` 查询参数传入，并保持相同 scope 与 `limit`。

## 运行示例

在仓库根目录运行。以下确定性示例只使用 Python 标准库与已提交的应用/公共模块：

```bash
PYTHONPATH=services/src PYTHONDONTWRITEBYTECODE=1 \
  uv run --python 3.14 --project services python - <<'PY'
import asyncio
from datetime import UTC, datetime
from uuid import UUID

from engrammesh.modules.memory.adapters import (
    InMemoryMemoryDatabase,
    InMemoryMemoryUnitOfWorkFactory,
)
from engrammesh.modules.memory.application.record_episode import (
    RecordEpisodeHandler,
)
from engrammesh.modules.memory.public import (
    MemoryScope,
    RecordEpisodeCommand,
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.shared.kernel.ids import (
    ArtifactId,
    CorrelationId,
    EventId,
    MemoryId,
    SubjectId,
    TenantId,
)


class Allow:
    async def authorize(self, request: object) -> bool:
        del request
        return True


class FixedClock:
    async def now(self) -> datetime:
        return datetime(2026, 7, 27, 9, 1, tzinfo=UTC)


class FixedIdentities:
    async def new_memory_id(self) -> MemoryId:
        return MemoryId(UUID(int=1))

    async def new_event_id(self) -> EventId:
        return EventId(UUID(int=2))


async def main() -> None:
    database = InMemoryMemoryDatabase()
    handler = RecordEpisodeHandler(
        authorization=Allow(),
        clock=FixedClock(),
        identities=FixedIdentities(),
        unit_of_work_factory=InMemoryMemoryUnitOfWorkFactory(database),
    )
    command = RecordEpisodeCommand(
        correlation_id=CorrelationId(UUID(int=3)),
        actor_id=SubjectId(UUID(int=4)),
        scope=MemoryScope(
            tenant_id=TenantId(UUID(int=5)),
            subject_id=SubjectId(UUID(int=6)),
            workspace_id="demo",
        ),
        source_type=SourceType.USER,
        content_ref=ArtifactId(UUID(int=7)),
        observed_at=datetime(2026, 7, 27, 9, 0, tzinfo=UTC),
        content_hash="sha256:demo",
        idempotency_key="demo-episode",
        sensitivity=Sensitivity.CONFIDENTIAL,
        retention_class=RetentionClass.STANDARD,
        consent_basis="user_request",
    )
    first = await handler.handle(command)
    replay = await handler.handle(command)
    print(f"first_created={first.created} replay_created={replay.created}")
    print(
        f"same_id={first.episode_id == replay.episode_id} "
        f"episodes={len(database.episodes)} events={len(database.events)}"
    )


asyncio.run(main())
PY
```

预期输出：

```text
first_created=True replay_created=False
same_id=True episodes=1 events=1
```

## 验证

在仓库根目录使用锁定的 Python 3.14 环境：

```bash
uv lock --check --python 3.14 --project services
uv run --python 3.14 --project services pytest \
  services/tests/contract/test_in_memory_memory_adapter_contract.py -q
ENGRAMMESH__POSTGRES__DSN=postgresql://engrammesh:engrammesh@localhost:5432/engrammesh \
  uv run --python 3.14 --project services pytest services/tests -q
uv run --python 3.14 --project services ruff check services/src services/tests
uv run --python 3.14 --project services mypy services/src
for suite in tools dco history links workflow orchestration external baseline yaml; do
  ./scripts/test-repository-policy.sh "$suite" || exit
done
```

仅 PostgreSQL 验证（启用 xdist loadgroup 时串行）：

```bash
ENGRAMMESH__POSTGRES__DSN=postgresql://engrammesh:engrammesh@localhost:5432/engrammesh \
  uv run --python 3.14 --project services pytest services/tests -m postgres -q
```

配置从 `ENGRAMMESH__` 变量读取，并用 `__` 分隔嵌套字段，例如 `ENGRAMMESH__TEMPORAL__NAMESPACE`。系统不会隐式加载 `.env`。生产环境验证对敏感遥测内容采集采取关闭失败策略，要求 PostgreSQL 使用 `sslmode=verify-full`，并要求 Temporal 启用 TLS。

## Adapter 契约义务

PostgreSQL Episode Adapter 已通过其类型化 Harness 绑定 `tests/contract/memory_adapter_contract.py` 中 `EPISODE_ADAPTER_CONTRACTS` 的每个断言，且未修改可复用断言主体。核心 Registry 不假定单一全局锁，也不要求 Claim 操作或游标不可用。可复用断言模块只导入公共记忆 Port、领域值与共享契约；应用编排由其他测试单独验证。`IN_MEMORY_CAPABILITY_CONTRACTS` 与 `POSTGRES_EPISODE_CAPABILITY_CONTRACTS` 分别描述各 Adapter 的不可用 Claim、拒绝游标与同步模型。

生产 PostgreSQL 的后续工作包括行级安全（RLS）策略，以及 Episode 摄取之外的更广泛记忆表面。HTTP 后续工作包括生产可观测性。新增共享能力行为需要单独评审的契约 Profile，而不是修改可移植 Episode 断言主体。

经过单独设计评审后，后续阶段可增加 Temporal Adapter、API、Worker 与外部事件分发。它们必须保留上述依赖与权威边界；本指南不预先授权任何供应商或可部署产品功能。
