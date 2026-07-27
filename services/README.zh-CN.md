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
│   │   │   ├── adapters/     # 用于测试/开发的内存事务 Adapter
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

- PostgreSQL 将作为记忆事实、版本化记录、追加事件和持久化结构快照的权威来源。
- Temporal Event History 将作为执行生命周期、定时器、重试和持久化工作流进度的权威来源。
- 对象存储将作为由不可变引用寻址的大型内容的权威来源。
- 向量索引、图存储、缓存、搜索索引和遥测是可重建投影或运行信号，绝不是主要权威来源。
- 通用契约与 Schema 定义稳定的形状和不变量。内存 Adapter 仅在单个进程内保留已提交的 Episode 与 Outbox 状态；它不提供持久化权威来源、外部分发或投影。

## 第三方 Adapter 策略

PostgreSQL 驱动、Temporal SDK、模型提供方、工具协议、对象存储、向量数据库、图数据库和遥测导出器必须在现有 Port 或经过单独评审的 Port 后实现。供应商类型、客户端、异常和重试策略不得泄漏到领域模型或模块公共契约中。Adapter 负责与稳定的 EngramMesh 类型相互转换，强制传递租户与授权上下文，并接受确定性契约测试。增加提供方依赖库还必须有具体的 Adapter 用例，不得提前推测性引入。

## Episode 摄取切片

`RecordEpisodeHandler` 是一个与框架无关的应用服务。它先完成授权，再使用注入的时钟与标识符 Port，按内容引用记录一个不可变 `Episode`。当前唯一具体的持久化实现是由 `InMemoryMemoryDatabase` 支持的 `InMemoryMemoryUnitOfWorkFactory`，仅供确定性测试和本地开发使用。

本切片明确不包含 HTTP、依赖注入装配、PostgreSQL、ORM 与迁移、Temporal、对象上传、Claim 提取、检索、纠正与删除、投影，以及外部 Outbox 分发。它不提供跨进程持久性或投递保证。

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

授权在事务开启前完成。无效命令值、领域值和 Adapter 错误会原样向上传播，因为与传输层有关的错误转换不属于本切片。

## 幂等与事务语义

幂等范围是 `(tenant_id, idempotency_key)`。第一次追加返回 `created=True`；同一租户内的重放返回原始 Episode ID 和 `created=False`，且不会暂存第二个事件。不同租户可以复用同一键。

内存 Adapter 使用一个进程内锁串行化事务，并采用写时复制状态。`commit()` 暂存新的已提交快照，而成功退出上下文才完成事务。未调用 `commit()` 就退出、抛出异常或被取消，都会丢弃暂存的 Episode、幂等索引与 Outbox 变更。在 `commit()` 之后、成功退出上下文之前发生异常或取消时，会恢复事务前快照。这是用于本地测试/开发的原子模型，不是生产级并发或持久化模型。

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
uv run --python 3.14 --project services pytest services/tests -q
uv run --python 3.14 --project services ruff check services/src services/tests
uv run --python 3.14 --project services mypy services/src
for suite in tools dco history links workflow orchestration external baseline yaml; do
  ./scripts/test-repository-policy.sh "$suite" || exit
done
```

配置从 `ENGRAMMESH__` 变量读取，并用 `__` 分隔嵌套字段，例如 `ENGRAMMESH__TEMPORAL__NAMESPACE`。系统不会隐式加载 `.env`。生产环境验证对敏感遥测内容采集采取关闭失败策略，要求 PostgreSQL 使用 `sslmode=verify-full`，并要求 Temporal 启用 TLS。

## 下一 Adapter 的义务

未来的 PostgreSQL Episode Adapter 必须通过自己的类型化测试 Harness 绑定 `tests/contract/memory_adapter_contract.py` 中的每个断言，且不得修改可复用断言主体。它还必须补充 PostgreSQL 专属的迁移、约束、事务隔离、租户强制与失败行为集成测试。Claim 持久化和游标支持在本切片中仍不可用；改变这些行为需要单独评审契约修订。

经过单独设计评审后，后续阶段可以增加显式组合根、PostgreSQL 或 Temporal Adapter、迁移、API、Worker 与外部事件分发。它们必须保留上述依赖与权威边界；本指南不预先授权任何供应商或可部署产品功能。
