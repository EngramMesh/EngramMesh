# EngramMesh 生产级架构设计

- 状态：待最终复核
- 日期：2026-07-26
- 仓库名：`engrammesh`
- 开源许可证：Apache License 2.0
- 产品定位：具备类人认知记忆和多 Agent 通用任务执行能力的多租户 AI Agent 平台
- 文档边界：产品与技术总纲、生产级架构及质量门禁；不包含具体实现

## 1. 目标

EngramMesh 面向普通用户、开发者和企业团队。平台允许用户创建 Agent、连接工具、执行长时间任务，并在多次交互和任务中形成可解释、可纠正、可遗忘的长期记忆。

第一阶段服务 100–1,000 名用户，架构需平滑扩展至万级用户、区域化部署和企业私有部署。默认采用云端 SaaS，同时保持模型、存储和执行环境可替换。

首个端到端场景是研究型 Agent：多个 Agent 联网调查主题、交叉验证并生成带来源报告；系统记住用户偏好、任务成败和有效策略，在后续相似任务中改善计划与输出。

本次工作只确定产品总纲、架构边界、状态所有权、演进方式、测试体系和验收规则，不编写业务代码，不部署基础设施，不创建远程 GitHub 仓库，也不承诺本设计已经完成实现。后续实施必须另行编写经过评审的实施计划。

## 2. 非目标

第一版不建设以下能力：

- Agent 或 Skill 商店
- 完整商业计费系统
- 手机端应用
- 自动付款、发信、发布或删除等高风险写操作
- 自训练基础模型
- 无限制递归创建 Agent
- 对人脑神经结构的完整科学仿真
- 跨区域主动双写

“类人记忆”指可观察的认知行为，而非宣称系统具有人类意识。需要实现的行为包括形成、巩固、联想召回、强化、衰减、冲突修正、遗忘和从经历中抽象策略。

## 3. 架构原则

1. 每类状态只有一个权威所有者。
2. 外部副作用必须幂等、可审计并受策略约束。
3. PostgreSQL 中的事件和业务数据是记忆事实源；向量和图数据是可重建投影。
4. 租户权限过滤先于任何检索或工具调用。
5. Agent 仅接收完成当前子任务所需的最小上下文。
6. 模型输出、工具输出和检索内容均视为不可信输入。
7. 记忆推断必须保存来源、置信度、有效时间和版本。
8. 算法、Prompt、Workflow、事件和投影 Schema 均须版本化。
9. 采用稳定版本政策，不以追逐预发布版本代替架构演进。
10. 先建设模块边界，再按安全、扩缩容和故障隔离需要拆分部署。

## 4. 总体架构

EngramMesh 采用 Cell-based 架构。

### 4.1 Global Control Plane

控制平面管理：

- 身份、组织、租户和成员关系
- Agent 定义、版本和发布状态
- 模型、工具、Memory Policy 和安全策略
- 配额、用量、Cell 分配和区域路由
- 全局功能开关和版本兼容信息

控制平面不保存用户记忆明文，不直接执行 Agent 任务。租户创建时固定分配至一个 Regional Cell。

### 4.2 Regional Cell

每个 Cell 包含：

- Control API 的区域数据接口
- Agent Runtime 和 Temporal Workers
- Memory Engine 与投影 Worker
- Tool Gateway、Model Gateway 和 Sandbox Pool
- PostgreSQL、Qdrant、GraphStore、Valkey 和对象存储接入
- 本 Cell 的观测、告警和审计出口

扩容优先增加 Cell，而不是无限扩大一个共享集群。单 Cell 故障不得影响其他 Cell。企业可获得独立数据分区、独立 Cell 或完整私有部署。

## 5. 状态所有权

| 状态类别 | 唯一事实源 | 说明 |
|---|---|---|
| 任务运行、暂停、重试、定时 | Temporal | Event History 是任务执行权威 |
| Agent 定义与业务数据 | PostgreSQL | 使用版本化记录和审计事件 |
| 认知记忆与证据 | PostgreSQL | 追加事件与版本，不原地覆盖历史 |
| Agent 图状态转换 | LangGraph | 作为状态机和规划库，不成为平台级执行事实源 |
| 语义检索索引 | Qdrant | 可从记忆事件重建 |
| 关系与因果图 | GraphStore 投影 | 默认使用 PostgreSQL 图关系表；Neo4j 是可选 Adapter；均可从记忆事件重建 |
| 缓存、限流、短期通知 | Valkey | 不保存不可恢复的核心状态；通过 Adapter 兼容 Redis |
| 文件和大型产物 | S3/MinIO | 使用内容哈希、版本和保留策略 |

## 6. 服务与代码边界

代码采用 monorepo：

```text
apps/
  web/

services/
  control_api/
  agent_runtime/
  memory_engine/
  workflow_worker/
  projection_worker/
  consolidation_worker/
  tool_gateway/
  model_gateway/
  sandbox_manager/

packages/
  contracts/
  evals/
  sdk_python/
  sdk_typescript/

infra/
  compose/
  helm/
  terraform/
  observability/
```

MVP 中，`control_api`、`agent_runtime` 和 `memory_engine` 是同一 Python 模块化单体的内部边界。Workflow、Projection 和 Consolidation 使用同一代码库的独立 Worker 入口。Tool Gateway、Model Gateway 和 Sandbox Manager 因安全边界不同而独立部署。

服务间契约位于 `packages/contracts`，采用 JSON Schema 或 Protobuf，并包含显式版本。模块不得跨边界直接访问其他模块的数据库表。

## 7. 推荐技术栈

| 层级 | 选型 |
|---|---|
| Web | Next.js 16、React 19、TypeScript、Tailwind CSS、shadcn/ui |
| 前端数据 | TanStack Query、Zustand、Server-Sent Events |
| 核心后端 | Python 3.14、FastAPI、Pydantic、SQLAlchemy 2、Alembic |
| Agent 状态机 | LangGraph 1.x 开源库，不依赖商业 Agent Server |
| 持久工作流 | Temporal |
| 业务与记忆事实源 | PostgreSQL 18 |
| 向量投影 | Qdrant |
| 图投影 | GraphStore SPI；PostgreSQL 关系图为默认实现，Neo4j 为可选 Adapter |
| 临时数据 | Valkey；通过兼容 Adapter 支持 Redis |
| 对象存储 | S3 或 MinIO |
| 模型网关 | LiteLLM Proxy 加 EngramMesh Provider Adapter |
| 工具协议 | MCP 加内部类型化 Tool API |
| 身份 | OIDC；SaaS 接 WorkOS/Auth0，私有部署接 Keycloak |
| 可观测性 | OpenTelemetry、Langfuse、Prometheus、Grafana、Loki |
| 工程工具 | uv、Ruff、mypy、pytest、pnpm、Turborepo、Playwright |
| 部署 | Docker Compose、Helm、Kubernetes、Terraform |

生产版本使用当前稳定版或前一个受支持稳定版。预发布版本只进入实验环境。依赖升级必须经过兼容性测试、离线 AI 评测、Workflow Replay 和灰度发布。

## 8. 认知记忆模型

### 8.1 记忆类型

- `working`：当前任务中的短期上下文
- `episodic`：具体时间、参与者、过程和结果
- `semantic`：相对稳定的事实、概念和偏好
- `procedural`：完成某类任务的策略、步骤和技能
- `self`：Agent 的角色、能力、边界和长期目标
- `prospective`：未来计划、承诺和提醒

### 8.2 记忆记录

每条记忆至少包含：

- 租户、用户、Agent 和作用域
- 类型、规范化内容和结构化命题
- 来源事件和证据引用
- 创建时间、事件时间和有效时间
- 置信度、重要性、新颖度和风险权重
- 访问、采用、确认、否定和任务贡献统计
- Memory Policy 和编码算法版本
- 隐私级别、保留策略和加密信息
- 当前状态与前一版本引用

### 8.3 生命周期

1. **感知**：对话、文件、工具结果和 Agent 行为写入不可变事件。
2. **注意**：依据目标相关性、新颖性、任务影响、频率、风险、用户指令和来源可信度评分。
3. **编码**：将高价值事件转换为一种或多种记忆类型，并建立证据关系。
4. **巩固**：后台 Consolidator 合并重复经历、抽象事实和程序、发现矛盾并更新图投影。
5. **召回**：并行使用 Qdrant、GraphStore、PostgreSQL 和情景/程序线索，再进行融合排序。
6. **强化**：只有被用户确认、重复验证或对任务产生正面贡献时才增加强度。
7. **纠错**：否定和失败结果降低置信度，创建纠错事件，不静默覆盖证据。
8. **衰减**：低价值记忆降低默认召回概率；重复情景压缩为抽象记忆。
9. **删除**：可识别内容与不可变事件信封分离保存。删除时清除在线 Payload、销毁对应数据密钥、清理投影与缓存，并在账本中保留不可逆 tombstone。备份中的密文按已声明保留期淘汰，系统产生标明完成层级的可验证回执。

### 8.4 冲突处理

命题采用版本和有效时间建模。新证据不会直接覆盖旧事实。自动解析必须满足证据质量和置信度阈值；高风险或无法解析的冲突交给用户确认。检索结果需要区分事实、用户声明、系统推断和未验证内容。

### 8.5 召回

召回顺序为：

1. 解析当前目标、主体、时间和权限作用域。
2. 在执行检索前应用租户和数据访问策略。
3. 并行生成语义、图关系、结构化和情景候选。
4. 根据相关性、时效性、置信度、重要性、来源质量和多样性重排。
5. 生成受 token、隐私和任务预算约束的 Memory Context Pack。
6. 记录候选、最终采用项和对任务结果的贡献，用于离线评测。

## 9. 多 Agent 执行

### 9.1 角色

- Orchestrator：理解目标并决定是否需要多 Agent
- Planner：生成带依赖和验收标准的任务图
- Worker：执行领域子任务
- Critic：验证事实、逻辑、风险和需求覆盖
- Synthesizer：解决冲突并形成最终产物
- Memory Steward：选择需要形成长期记忆的经历
- Safety Guardian：执行权限、风险和预算策略

这些是职责而非固定进程。简单任务由单 Agent 承担多个职责；只有可并行、上下文需要隔离或专业能力明显不同时才创建多个 Worker。

### 9.2 执行流程

```text
用户目标
  -> 能力、权限和风险分析
  -> 生成结构化任务依赖图
  -> 匹配 Agent、Skill、模型和工具
  -> Temporal 调度可执行节点
  -> Worker 执行并输出结构化结果
  -> Critic 按验收标准检查
  -> 定向返工或人工介入
  -> Synthesizer 汇总
  -> Memory Steward 生成复盘和候选记忆
```

每个任务节点包含输入、预期输出、负责角色、依赖、工具权限、模型能力、超时、预算、重试策略、验收条件和审批要求。

### 9.3 Temporal 与 LangGraph 边界

Temporal 是唯一持久执行权威。Workflow 只包含确定性控制逻辑，所有网络、数据库、LLM、工具、文件和沙箱操作均在 Activity 中完成。

LangGraph 用于生成和推进 Agent 状态机。LangGraph 节点产生状态更新或动作意图；有副作用的动作由 Temporal Activity 执行。不得让 LangGraph 和 Temporal 同时对同一个副作用实施跨进程重试。

Activity 采用 `workflow_run_id + activity_id + logical_action_id` 作为稳定幂等键。模型调用保存请求指纹、模型版本、Prompt 版本和结果引用。错误分为瞬时、间歇、永久、用户可修复、策略阻止和系统缺陷，并配置不同处理策略。

Temporal Event History 只保存小型确定性状态、版本和内容引用。完整 LangGraph 状态与结构化中间结果保存在 PostgreSQL，大型输入、输出和文件保存在 S3/MinIO；引用必须包含租户、内容哈希、Schema 版本和加密上下文。Temporal Payload 使用加密 Codec，长任务通过 Continue-As-New 控制 Event History 大小。Workflow Replay 不得重新执行 LLM 或外部工具调用。

### 9.4 上下文隔离

Worker 只接收子目标、必要记忆、上游结构化结果、被授权工具和预算。Agent 间不复制完整对话或隐藏推理。所有跨 Agent 输出通过版本化 Schema 验证。

## 10. 事件与投影

PostgreSQL Transactional Outbox 保证业务写入和事件发布的一致性。初期 Projector 直接读取 Outbox；吞吐或消费者数量增加后，引入 Kafka/Redpanda。Valkey/Redis Streams 不承载长期领域事件。

事件信封包含：

- `event_id`
- `event_type`
- `schema_version`
- `tenant_id`
- `aggregate_id`
- `aggregate_version`
- `correlation_id`
- `causation_id`
- `occurred_at`
- `payload`

消费者使用 Inbox 表和事件 ID 去重。事件 Schema 只允许向后兼容演进；破坏性变更发布新事件类型。Projection Worker 保存消费水位、投影版本、校验和和失败原因。

Qdrant、GraphStore、embedding 模型或记忆算法升级采用并行版本投影：

```text
v1 当前读取
v2 后台重建
v1/v2 影子双读和评测
切换读取别名
观察期后回收 v1
```

投影延迟超过阈值时，系统显示降级状态，并回退至 PostgreSQL 的结构化和全文检索。

## 11. 多租户与数据隔离

平台提供三种隔离等级：

1. **Shared**：PostgreSQL RLS、Qdrant shard key/payload 分区、经强制租户查询网关访问的共享 GraphStore。
2. **Isolated**：独立 PostgreSQL Schema、Qdrant Collection 和 GraphStore 分区或数据库。
3. **Dedicated**：独立 Regional Cell 或完整私有部署。

所有数据访问经过不可绕过的 Tenant Context 和授权 Repository。数据库连接设置租户上下文，后台任务显式携带租户身份。禁止业务代码自行拼接租户过滤条件。

CI 和预生产环境执行跨租户属性测试与模糊测试。对象存储使用租户前缀和独立加密上下文。大型企业租户可迁移隔离等级，迁移通过双写校验和可回滚切换完成。

共享 GraphStore 不允许业务服务执行任意查询，只能通过独立 Graph Query Service 使用受控模板访问。所有节点和关系必须由租户锚点进入，使用包含 `tenant_id` 的复合唯一键和受限数据库凭据。Neo4j Adapter 禁止向业务层暴露任意 Cypher。若自动化测试不能证明隔离不变量，包含敏感长期记忆的租户不得使用 Shared 图，必须升级到 Isolated 或 Dedicated。

## 12. 工具与安全

Tool Gateway 对 MCP 和内部工具执行零信任控制：

- Server 来源、签名、版本和哈希校验
- Tool Schema、能力、风险和数据分类声明
- OAuth token audience 限制与每任务短期凭据
- 凭据保存在 Vault/KMS，不进入 Agent 上下文
- 默认拒绝出站网络，只开放允许域名
- 沙箱采用只读基础镜像、临时文件系统和资源限制
- 工具响应标记来源与信任级别，并进行提示注入扫描
- 污染标记随数据在 Agent、记忆和产物链路中传播
- 高风险操作采用 `prepare -> approve -> commit`
- 所有工具调用保存参数摘要、授权、结果和审计事件

Memory Admission Policy 阻止不可信信息直接成为长期指令。被污染、来源未知或仅由外部内容支持的信息只能先进入隔离的情景证据，不能自动升格为程序性、自我或高置信语义记忆。升格至少需要用户确认、受信工具证明或两个相互独立来源的交叉验证。污染标记在摘要、巩固、合并和跨 Agent 传递中不得丢失。

高风险操作的批准必须绑定动作规范化摘要、目标资源、参数哈希、批准人、有效期和策略版本。任何参数变化、超时或策略升级都会使原批准失效，避免批准后替换目标的时序攻击。

平台支持租户级模型、工具和数据驻留策略。敏感记忆使用字段级信封加密。Trace 默认不记录明文 Prompt、记忆或工具结果。

## 13. 模型网关

Model Gateway 不把不同模型假设为完全等价。每个模型记录：

- 原生工具调用和结构化输出能力
- 上下文、输出和多模态限制
- 数据驻留、保留和合规属性
- 延迟、价格、限流和稳定性
- 角色适用性和离线评测成绩

路由先匹配能力与数据策略，再优化成本和延迟。自动回退仅发生在能力等价且合规策略一致的模型之间。Prompt、模型参数、解析器和路由策略均版本化。

模型密钥由 Vault/KMS 管理，LiteLLM 部署于受限网络中。服务通过短期内部身份调用网关，不持有上游供应商密钥。

## 14. 可观测性与 SRE

### 14.1 SLO

- 核心 API 月可用性：99.9%
- 已接受的任务不会因 Worker 重启而丢失
- PostgreSQL：RPO 不超过 5 分钟，RTO 不超过 30 分钟
- Temporal Persistence：RPO 不超过 5 分钟，RTO 不超过 30 分钟
- Control Plane 配置与租户路由：RPO 不超过 5 分钟，RTO 不超过 15 分钟
- KMS/Vault 与对象存储：采用多可用区服务；密钥不可用时进入安全停写而非明文降级
- Qdrant/GraphStore：允许从事实源重建，单 Cell 完整重建目标不超过 8 小时
- 单 Cell 故障不影响其他 Cell
- 投影可从 PostgreSQL 事件完整重建
- 跨租户数据泄漏容忍度为零

用户可感知 SLI 还包括任务接受延迟、任务恢复时间、投影最大陈旧时间、队列公平性、审批等待状态准确率和删除完成时间。具体阈值由 SLO Policy 版本化管理，降低阈值必须经过 ADR、风险批准和用户影响评估。

### 14.2 观测

统一使用 OpenTelemetry Trace、Metric 和 Log，并贯穿 `tenant_id` 的不可逆标识、`task_id`、`workflow_id`、`agent_version`、`prompt_version` 和 `model`。

关键指标包括：

- API 和任务成功率、延迟和积压
- Temporal Activity 重试和永久失败
- Outbox 与投影延迟
- Qdrant/GraphStore 检索延迟和降级次数
- 模型 token、费用、限流和回退
- 每租户并发、配额和公平性
- 记忆提取、召回、干扰和纠错指标
- 沙箱和工具策略阻止事件

每季度执行 PostgreSQL、Temporal、对象存储、KMS/Vault 和完整 Cell 的恢复演练。恢复顺序为身份与密钥、Control Plane 路由、PostgreSQL/Temporal、对象存储、在线 API、查询投影和后台巩固。告警必须链接到 Runbook。生产数据库、Temporal、Qdrant 和启用的 GraphStore Adapter 采用多可用区或托管高可用形态；对象存储启用版本和生命周期策略。

## 15. 可持续演进与发布

- AgentSpec、MemoryPolicy、ToolSpec、Prompt、Workflow、事件和投影全部版本化。
- Temporal Workflow 修改使用安全 patch/version 和 Replay 测试。
- 数据库迁移采用 expand、migrate、contract 三阶段。
- API 和事件契约执行兼容性检查。
- 使用 Feature Flag、影子流量、租户级灰度和自动回滚。
- GitOps 管理部署状态，Terraform 管理基础设施。
- 构建产物生成 SBOM，执行依赖、镜像、许可证和密钥扫描。
- 依赖升级由自动化工具发起，但必须通过完整回归和 AI 评测门禁。
- 模块以公开接口交互；是否拆分为微服务由扩缩容、安全或故障隔离证据决定。
- 使用 ADR 记录重要架构选择、替代方案和迁移触发条件。

## 16. 评测与测试

### 16.1 记忆评测

- 重要信息提取准确率和召回率
- 将推断误记为事实的比例
- 召回命中率与无关记忆干扰率
- 冲突识别和正确版本选择率
- 用户纠错后的错误复用率
- 来源可追溯率
- 低价值记忆衰减效果
- 历史经验对相似任务的改善程度
- 删除在全部投影中的完成率

评测集覆盖时间变化、用户反悔、相似实体、错误来源、恶意提示、长期多轮和跨任务迁移。

### 16.2 多 Agent 评测

- 最终任务成功率
- 计划依赖正确率
- 子任务一次验收通过率
- Critic 真阳性和误报率
- Agent 结果冲突率
- 工具调用成功率
- 人工介入次数
- 单 Agent 与多 Agent 的质量、成本和延迟差值

### 16.3 测试分层

- 单元测试：评分、衰减、冲突、权限、路由和状态机
- 属性测试：幂等性、版本链和租户隔离不变量
- 集成测试：使用 Testcontainers 启动数据与工作流依赖
- Workflow Replay：验证旧任务可由新代码安全重放
- 契约测试：API、事件、Agent 输出和工具 Schema
- E2E：创建 Agent、执行任务、审批、纠错和删除
- 混沌测试：Worker、模型、数据库和网络故障
- 安全测试：越权、提示注入、恶意 MCP、凭据和出站网络
- 离线 AI 评测：固定数据集、模型快照和预算
- 在线灰度：仅对授权流量执行，并支持即时回滚

### 16.4 完整测试与需求追踪

每项已批准需求必须在版本化追踪矩阵中关联：

```text
requirement_id
  -> architecture_contract
  -> risk_class
  -> test_case_ids
  -> test_level
  -> owner
  -> release_evidence
```

任何没有测试证据的生产需求都视为未完成。测试数据、模型快照、Prompt、评分器、随机种子和环境镜像必须版本化。关键测试不允许跳过；不稳定测试必须立即阻断发布并修复，不能通过重跑直到成功来放行。

完整回归集至少覆盖：

- API、SDK、事件和数据库 Schema 向后兼容
- 历史 Temporal Workflow Replay
- 数据库 expand/migrate/contract 升级路径
- Qdrant/GraphStore 全量重建和新旧投影等价性
- 租户、用户、Agent 和记忆作用域隔离
- 记忆形成、召回、纠错、衰减、删除和投毒防护
- 单 Agent、多 Agent、失败恢复、取消和人工审批
- MCP、模型回退、凭据、沙箱和出站网络策略
- 备份恢复、降级、限流、公平调度和容量边界
- Web 核心用户路径、无障碍和受支持浏览器
- 延迟、吞吐、token、模型费用和基础设施成本

### 16.5 不回归发布门禁

“不回归”分为确定性零回归和概率性非劣化：

- 安全、租户隔离、数据完整性、幂等性、删除、契约兼容和 Workflow Replay 必须零失败。
- 全部已修复生产缺陷必须保留永久回归用例。
- 记忆提取 F1、召回 nDCG 和来源可追溯率相对已发布基线下降不得超过 1 个百分点。
- 固定任务集的成功率采用 95% 置信区间，非劣化边界为 2 个百分点。
- p95 延迟、token 和单位任务费用不得恶化超过 10%，除非质量显著提升且经过书面风险批准。
- 任何模型、Prompt、Memory Policy、Tool、Workflow、依赖或基础设施变更都必须运行受影响测试和完整夜间回归。
- 发布产物必须关联测试报告、评测基线、已知风险、灰度范围和回滚版本。

确定性门禁失败时禁止发布。概率性门禁失败时默认禁止发布，只能通过限时、限租户实验重新收集证据，不能直接替换生产基线。

## 17. 后续实施分期总纲

本节只定义未来实施边界和依赖顺序，不代表本次开始实现。

### 17.1 生产底座与单 Agent

- 单 Cell、OIDC、租户上下文、PostgreSQL、Temporal 和对象存储
- AgentSpec、模型网关、基础工具网关和完整审计
- 单 Agent 研究任务、证据链、预算与人工审批
- CI/CD、可观测性、备份恢复和确定性回归门禁

### 17.2 核心长期记忆

- 情景与语义记忆、证据、版本、纠错和删除
- Qdrant 版本化投影与 PostgreSQL 降级检索
- 记忆查看、来源解释和用户控制
- MemoryBench 与记忆投毒防护

### 17.3 多 Agent 与程序性记忆

- Planner、并行 Worker、Critic 和 Synthesizer
- 上下文隔离、结构化协作和任务复盘
- 程序性记忆、强化、衰减和跨任务迁移评测
- 混沌测试、成本门禁和公平调度

### 17.4 图谱与企业能力

- GraphStore 版本化投影、自我与前瞻记忆；Neo4j 作为可选规模化 Adapter
- Isolated/Dedicated 租户迁移
- 企业 OIDC/SSO、数据驻留和私有部署
- 多 Cell 路由、故障隔离和容量扩展

每个阶段都必须形成可独立上线、可回滚、可观测的纵向切片，并通过该阶段对应的全部回归门禁后才能进入下一阶段。

前期使用 PostgreSQL Outbox 直接驱动投影，但保留标准 Event Publisher 接口。当持续吞吐、消费者数量或跨服务重放需求达到运维阈值时接入 Kafka/Redpanda，无需修改领域写入逻辑。

## 18. 验收标准

设计实现可进入生产试运行需同时满足：

1. Worker 在任意任务节点崩溃后能够恢复，且外部副作用不重复。
2. Qdrant 和启用的 GraphStore 投影被清空后能从 PostgreSQL 重建并通过校验。
3. 自动测试无法跨租户读取记忆、任务、文件或工具凭据。
4. 用户纠正一条错误记忆后，系统停止把旧版本作为当前事实使用。
5. embedding 或记忆算法能够通过影子投影和别名切换无停机升级。
6. 多 Agent 在固定研究任务集上相对单 Agent 有可量化质量提升，且成本在配置预算内。
7. 高风险工具调用在缺少有效批准时无法执行。
8. 备份恢复演练达到 RPO/RTO 目标。
9. 每次发布通过 Workflow Replay、契约测试、安全测试和 AI 评测门禁。
10. 用户能够查看记忆来源、纠正记忆并获得可验证的删除结果。
11. 所有已批准需求都能追踪到自动化测试和发布证据。
12. 确定性回归为零，概率性 AI 指标满足非劣化门禁。

## 19. 开源项目策略

### 19.1 许可证与贡献

EngramMesh 核心代码、CLI、SDK、示例和测试代码采用 Apache License 2.0。文档采用 CC BY 4.0。评测数据、模型、录制响应和第三方素材必须分别标明来源、用途和许可证，不因位于本仓库而自动继承代码许可证。

项目使用 Developer Certificate of Origin（DCO）接收贡献，提交必须包含 `Signed-off-by`。当前不要求 Contributor License Agreement。若未来考虑双许可证或 open-core 模式，必须先通过公开 RFC、法律审查和治理流程，不能静默更改既有贡献的许可。

`EngramMesh` 名称和标识由独立 `TRADEMARKS.md` 管理。Apache 2.0 代码许可证不自动授予项目商标使用权。

### 19.2 依赖许可政策

- 默认参考栈只能强依赖 OSI 批准且可合法再分发的组件。
- 核心功能不得依赖商业版、托管版或源代码可用但非开源的专有功能。
- 强 copyleft、source-available 和商业组件只能通过进程外 Adapter 或可选部署 Profile 接入。
- Valkey 是默认临时数据组件；Redis 通过兼容 Adapter 接入。
- PostgreSQL 图关系投影是默认 GraphStore；Neo4j 是可选 Adapter，不作为运行核心功能的前提。
- LangGraph 只使用 MIT 许可的开源库能力，不依赖商业 Agent Server。
- 每次发布生成 SPDX/CycloneDX SBOM、`NOTICE` 和 `THIRD_PARTY_NOTICES.md`，并执行自动许可证策略检查。

具体分发和依赖组合上线前仍需法律审查；架构策略不构成法律意见。

### 19.3 离线可贡献

任何贡献者都必须能够在没有付费模型、云账号或商业许可证的条件下运行完整确定性测试。项目提供：

- `MockModelProvider`：确定性生成工具调用和结构化输出
- `ReplayModelProvider`：使用脱敏、版本化的录制响应
- OpenAI-compatible 本地模型 Adapter
- 固定 Prompt、模型能力描述和评测基线
- 一条命令启动的本地开发 Profile
- 不包含外部密钥的默认 CI

真实供应商模型测试属于可选 Nightly Suite，使用受保护的项目凭据运行。外部模型波动不能阻断普通贡献者验证代码；但涉及 Provider Adapter 的发布必须通过对应供应商契约测试。

### 19.4 治理与社区

公开仓库至少包含：

- `README.md`
- `LICENSE`
- `NOTICE`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`
- `SUPPORT.md`
- `GOVERNANCE.md`
- `ROADMAP.md`
- `TRADEMARKS.md`
- `CHANGELOG.md`
- `THIRD_PARTY_NOTICES.md`
- `.github/CODEOWNERS`
- Issue、RFC 和 Pull Request 模板

`GOVERNANCE.md` 定义 Contributor、Reviewer 和 Maintainer 的职责、晋升和移除规则。重大架构、兼容性、许可证与治理变更使用公开 RFC；技术决策记录为 ADR。安全漏洞通过私密渠道报告，并使用协调披露流程。

### 19.5 发布与供应链

- 使用 Semantic Versioning 和公开弃用周期。
- `main` 分支启用保护规则、必需评审、CODEOWNERS 和必需状态检查。
- GitHub Actions 固定到完整 commit SHA。
- 发布产物生成 SBOM、来源证明和签名。
- 启用依赖更新、静态分析、Secret Scanning、OpenSSF Scorecard 和 OSPS Baseline 自评。
- 容器、Python 包、npm 包和 CLI 必须能够追溯至同一 Git commit 和不可变构建记录。
- 安全支持矩阵明确列出当前版本和仍接收安全修复的旧版本。

## 20. 核心架构结论

EngramMesh 的目标架构为：

> Cell-based SaaS + Temporal 单一执行权威 + PostgreSQL 事件源 + 版本化认知投影 + LangGraph 状态机 + 零信任工具平面。

该结构允许平台从一个生产 Cell 起步，通过增加 Cell、提升租户隔离等级和替换投影实现扩展，而无需改变认知记忆与 Agent 执行的核心领域模型。

本设计文档到此结束。本次不进入实现；具体目录、接口、表结构、事件字段细节、Workflow 代码、部署清单和测试用例将在后续实施计划与分阶段规格中定义。
