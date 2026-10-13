# ADR-0004：V1 单机 Docker Compose 部署

Status: Accepted  
Date: 2026-07-27

## Context

系统是内部单人工作台，生产流量有限，但包含客户隐私、模型密钥和重要内容版本，需要 HTTPS、备份和可回滚。托管 Kubernetes 或多主机集群成本与复杂度不匹配。

## Decision

生产基线是一台 Linux 云主机，使用 Docker Compose 运行 Caddy、API、Worker 和 PostgreSQL。Caddy 提供 HTTPS，数据库不开放公网。数据库与文件卷每日加密备份到主机外位置。

## Consequences

- 部署和恢复路径清晰，基础成本可控。
- 主机是可用性单点；目标 RPO 24 小时、RTO 8 小时。
- 云主机、域名和备份存储的采购与部署仍需独立生产授权。

## Revisit when

恢复目标收紧、容量达到 70%、单机故障影响不可接受，或需要跨地域容灾。
