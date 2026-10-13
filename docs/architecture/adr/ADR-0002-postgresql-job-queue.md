# ADR-0002：V1 使用 PostgreSQL 后台任务队列

Status: Accepted  
Date: 2026-07-27

## Context

文件解析、模型调用、诊断、导出和监测需要异步、幂等、可重试和可审计。首版负载有限，引入 Redis 和独立队列会增加部署、备份和故障面。

## Decision

任务保存在 PostgreSQL `jobs/job_attempts/job_events` 表。Worker 使用 `FOR UPDATE SKIP LOCKED` 领取，支持优先级、最大三次显式重试、超时、取消和进度。前端轮询任务状态。

## Consequences

- 业务记录与任务创建可以在同一事务提交。
- 队列吞吐受到数据库影响，需要索引、短事务和清理策略。
- 不提供高吞吐发布订阅或跨服务事件流。

## Revisit when

队列连续 7 天 P95 等待超过 10 分钟、每日任务明显超过 3000，或需要多个独立消费者服务。
