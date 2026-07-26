# Roadmap

This roadmap describes intended implementation sequencing from the approved
architecture. It is non-binding: all dates are not promises.

## 1. Production foundation and single-agent vertical slice

Establish a single Cell with OIDC, tenant context, PostgreSQL, Temporal, and
object storage. Add AgentSpec, model and tool gateways, auditability, and a
single-agent research workflow with evidence, budgets, and human approval.

**Quality gate:** a deployable, observable, rollback-capable vertical slice
passes deterministic regression, workflow recovery, backup/restore, and
security-policy checks.

Dates are not promises.

## 2. Episodic and semantic long-term memory

Add episodic and semantic memory, evidence, versioning, correction, deletion,
versioned Qdrant projections, PostgreSQL fallback retrieval, and user-facing
memory inspection and controls.

**Quality gate:** projections can be rebuilt from PostgreSQL; permission checks,
memory correction and deletion behavior, MemoryBench, and memory-poisoning
defenses pass their regression gates.

Dates are not promises.

## 3. Multi-agent execution and procedural memory

Introduce Planner, parallel Workers, Critic, and Synthesizer roles with
context isolation, structured collaboration, task retrospectives, and
procedural-memory reinforcement, decay, and cross-task transfer evaluation.

**Quality gate:** multi-agent workflows meet replay, chaos, cost-budget, fair
scheduling, and task-quality evaluation gates without weakening isolation or
approval controls.

Dates are not promises.

## 4. Graph projections, prospective/self memory and enterprise isolation

Add versioned GraphStore projections, prospective and self memory, optional
Neo4j scaling adapters, isolated/dedicated tenant migration, enterprise
OIDC/SSO, data residency, private deployment, multi-Cell routing, fault
isolation, and capacity expansion.

**Quality gate:** graph projections rebuild correctly, tenant isolation holds
across migration and routing, and enterprise deployment, resilience, and
capacity gates pass.

Dates are not promises.

Each milestone must be independently deployable, rollback-capable, and
observable before work proceeds to the next one.
