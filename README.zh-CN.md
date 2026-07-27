# EngramMesh

> 开源认知记忆与持久化多 Agent 运行平台。

简体中文 | [English](README.md)

## 状态

经过测试的架构脚手架已经启动；尚未实现任何运行时 Adapter 或产品功能。参阅[中文服务架构代码指南](services/README.zh-CN.md)。

## 为什么选择 EngramMesh

聊天历史是短暂的，难以检查，而且在长时间运行的工作中容易丢失所需上下文。仅依靠向量的 RAG 可以检索相似文本，但本身无法建模证据、时间、纠错、访问边界或任务执行的权威性。EngramMesh 围绕可解释、可版本化、可纠正并受权限治理的持久记忆而设计，同时支持可靠的多 Agent 工作。

## 核心原则

- 可解释、可版本化且可纠正的记忆，并保留证据和来源。
- Temporal 作为任务生命周期和重试的持久执行权威。
- PostgreSQL 作为记忆事实源，使用追加事件和版本化记录。
- 可重建的向量和图投影，而不是不可恢复的主状态。
- 零信任工具和保留权限边界的派生记忆。
- 提供方中立的模型和存储 Adapter，避免核心行为耦合到单一供应商。

## 架构

参阅[生产级架构](docs/architecture/engrammesh-production-architecture.md)。

## 路线图

参阅[非约束性路线图](ROADMAP.md)。

## 贡献

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)、[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
和 [SECURITY.md](SECURITY.md)。

## 许可证

代码采用 Apache License 2.0；文档采用 CC BY 4.0。
