# EngramMesh 服务架构脚手架

简体中文 | [English](README.md)

## 目的与明确的非目标

本目录包含经过测试的 EngramMesh Python 3.14 服务架构脚手架。它定义了不可变的共享标识符与事件元数据、记忆模块和持久化运行时的公共契约、依赖规则、类型化进程配置，以及带版本的 JSON Schema 事件契约。

它**不**包含可运行服务、依赖注入容器、数据库或 Temporal 客户端、API、Worker、持久化实现、模型或工具集成、投影流水线或任何产品功能。测试通过只能证明架构契约成立，并不表示已经存在可部署的运行时。

## 模块树

```text
services/
├── src/engrammesh/
│   ├── bootstrap/
│   │   └── settings.py       # 类型化、不可变的配置边界
│   ├── modules/
│   │   ├── memory/
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
    ├── contract/             # 公共契约与 JSON Schema
    └── unit/                 # 纯不变量与配置测试

packages/contracts/jsonschema/
├── events/v1/               # 通用事件信封
├── memory/v1/               # 记忆事件载荷
└── runtime/v1/              # 运行时事件载荷
```

## 依赖方向

共享内核只能依赖 Python 标准库。模块领域层可以依赖标准库、共享内核、自身领域层，以及其他模块严格限定的 `public.py` 契约。它不得导入其他模块的内部实现、自身的公共门面、Adapter 或第三方包。Port 与公共门面向内指向领域契约。`bootstrap/settings.py` 是当前脚手架中唯一使用 Pydantic Settings 的边界；领域代码保持与框架无关。

```text
bootstrap/配置                 模块公共契约
      |                              |
      v                              v
未来组合根 -> 未来应用服务 -> Port -> 领域层
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
- 本脚手架中的契约与 Schema 只定义形状和不变量；它们不持久化、调度、发布或投影任何状态。

## 第三方 Adapter 策略

PostgreSQL 驱动、Temporal SDK、模型提供方、工具协议、对象存储、向量数据库、图数据库和遥测导出器必须在现有 Port 或经过单独评审的 Port 后实现。供应商类型、客户端、异常和重试策略不得泄漏到领域模型或模块公共契约中。Adapter 负责与稳定的 EngramMesh 类型相互转换，强制传递租户与授权上下文，并接受确定性契约测试。增加提供方依赖库还必须有具体的 Adapter 用例，不得提前推测性引入。

## 运行测试与静态检查

在仓库根目录使用锁定的 Python 3.14 环境：

```bash
uv lock --python 3.14 --project services
uv run --python 3.14 --project services pytest services/tests -q
uv run --python 3.14 --project services ruff check services/src services/tests
uv run --python 3.14 --project services mypy services/src
for suite in tools dco history links workflow orchestration external baseline yaml; do
  ./scripts/test-repository-policy.sh "$suite"
done
```

配置从 `ENGRAMMESH__` 变量读取，并用 `__` 分隔嵌套字段，例如 `ENGRAMMESH__TEMPORAL__NAMESPACE`。系统不会隐式加载 `.env`。生产环境验证对敏感遥测内容采集以及不安全的 PostgreSQL 或 Temporal 传输采取关闭失败策略。

## 下一实现阶段可以增加什么

经过单独设计评审后，下一阶段可以增加编排现有 Port 的应用服务、小型显式组合根、具体 PostgreSQL 与 Temporal Adapter、数据库迁移、API、Worker，以及确定性 Adapter 契约测试。公共契约只能通过经过评审的版本化变更进行扩展。下一阶段必须保留上述依赖与权威边界；本指南不预先授权任何供应商或产品功能。
