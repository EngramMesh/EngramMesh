# EngramMesh 服务架构脚手架

简体中文 | [English](README.md)

## 目的与明确的非目标

本目录包含经过测试的 EngramMesh Python 3.14 服务架构脚手架，以及一个经过测试的 Episode 摄取应用切片。它定义了不可变的共享标识符与事件元数据、记忆模块和持久化运行时的公共契约、依赖规则、类型化进程配置、带版本的 JSON Schema 事件契约，以及仅用于测试与开发的事务型内存 Adapter。

它**不**包含可运行服务、依赖注入容器、生产数据库或 Temporal 客户端、API、Worker、外部事件分发器、模型或工具集成、投影流水线或可部署产品功能。内存 Adapter 仅在单个进程内保存状态，并不持久化。测试通过只能证明本文所述应用契约与架构契约成立，并不表示已经存在可部署的运行时。

## 模块树

```text
services/
├── src/engrammesh/
│   ├── bootstrap/
│   │   └── settings.py       # 类型化、不可变的配置边界
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
未来组合根 -> 应用服务 -> Port -> 领域层
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

本切片明确不包含 HTTP、依赖注入装配、`PostgresSettings` 组合根绑定、Temporal、对象上传、Claim 提取、检索、纠正与删除、投影，以及外部 Outbox 分发。内存 Adapter 不提供跨进程持久性或投递保证。

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

租户隔离通过 SQL 谓词强制（每次读写均带 `tenant_id`）。PostgreSQL 行级安全（RLS）策略推迟到后续生产加固切片。`PostgresSettings` 已存在于 `bootstrap/settings.py`，但本切片未将其接入 Adapter；未来的组合根将读取 `ENGRAMMESH__POSTGRES__DSN` 并构造 `PostgresMemoryDatabase`。

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

生产 PostgreSQL 的后续工作包括行级安全（RLS）策略、通过显式组合根接入 `PostgresSettings`，以及 Episode 摄取之外的更广泛记忆表面。新增共享能力行为需要单独评审的契约 Profile，而不是修改可移植 Episode 断言主体。

经过单独设计评审后，后续阶段可增加 Temporal Adapter、API、Worker 与外部事件分发。它们必须保留上述依赖与权威边界；本指南不预先授权任何供应商或可部署产品功能。
