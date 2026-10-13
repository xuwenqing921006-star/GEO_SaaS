# 产品状态模型

Status: 阶段 C 定稿

## 客户

```mermaid
stateDiagram-v2
    [*] --> active: 创建客户
    active --> paused: 暂停代运营
    paused --> active: 恢复代运营
    active --> archived: 归档
    paused --> archived: 归档
    archived --> active: 恢复
```

## 内容

```mermaid
stateDiagram-v2
    [*] --> brief: 创建内容简报
    brief --> generating: 发起生成
    generating --> draft: 生成完成
    generating --> blocked: 事实或合规阻断
    generating --> failed: 模型或系统失败
    failed --> generating: 显式重试
    blocked --> draft: 人工修复并复核
    draft --> checked: 检查完成
    checked --> optimized: GEO 优化或自然化
    optimized --> exported: 导出
    checked --> exported: 直接导出
    draft --> archived: 归档
    checked --> archived: 归档
    optimized --> archived: 归档
```

## 后台任务

```mermaid
stateDiagram-v2
    [*] --> queued: 幂等创建
    queued --> running: Worker 领取
    queued --> cancelled: 用户取消
    running --> succeeded: 结果事务提交
    running --> failed: 超时或错误
    failed --> queued: 显式重试并增加 attempt
```

## 状态转换规则

| 对象 | 触发 | 前置条件 | 副作用 | 失败行为 |
|---|---|---|---|---|
| 客户 | 归档 | 无运行中任务 | 阻止新生成与监测，历史只读 | 有运行任务返回 409 |
| 内容 | 发起生成 | 简报存在、最小事实门槛通过 | 冻结事实快照并创建任务 | 事实不足返回 422 |
| 内容 | 优化/自然化 | 已有草稿 | 创建不可变新版本并再次事实检查 | 事实漂移时进入 blocked |
| 任务 | 领取 | `queued` 且重试时间已到 | 行锁更新为 `running` | 未获取锁则跳过 |
| 任务 | 重试 | `failed` 且未超过 3 次 | 创建新 attempt，保留历史错误 | 超过次数返回 409 |
| 监测批次 | 完成 | 所有样本成功或失败已落库 | 汇总指标并生成反馈候选 | 不把失败样本计为未提及 |
