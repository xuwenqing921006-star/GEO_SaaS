# ADR-0001：V1 采用模块化单体

Status: Accepted  
Date: 2026-07-27

## Context

系统首版只有一名直接使用者，目标容量为 100 个活跃客户。客户、知识、策略、内容和监测需要强事务一致性，团队规模与运维资源都不支持微服务开销。

## Decision

使用一个 FastAPI 部署单元和一个共用领域包的 Worker。代码按 `auth/clients/knowledge/strategy/content/channels/monitoring/providers/jobs/settings/storage` 模块隔离，模块之间通过应用服务与 DTO 调用。

## Consequences

- 可以使用单一事务和统一权限边界，开发与部署简单。
- 模块需要通过代码审查和依赖测试防止边界退化。
- Worker 可独立扩容，但领域代码与 API 版本必须一致。

## Revisit when

单机纵向扩容后仍无法满足容量、模块需要独立发布节奏，或出现明确的团队所有权边界。
