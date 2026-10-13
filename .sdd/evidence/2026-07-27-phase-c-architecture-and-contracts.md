# 阶段 C 产品设计与架构证据

日期：2026-07-27  
范围：仅 Web 网页版

## 用户决定

- 产品负责人确认进入阶段 C。
- 产品负责人明确 V1 只建设 Web 网页，不建设小程序、桌面安装包、原生移动 App 或其他客户端。
- B2 高保真原型已确认，`docs/prototypes/index.html` 作为生产 Web 的信息与视觉基准，不直接作为生产源码。

## 定稿产物

- `docs/PRD.md`：最终路线图、架构蓝图、原型映射、核心流程、组件交互、风险、迁移与回滚。
- `docs/api-contracts.md`：65 个 HTTP 接口，完整共享 DTO、请求、成功响应和错误响应。
- `docs/Plan.md`：Web 前端、后端、外部服务、开发顺序、测试、用户门禁和发布计划。
- `docs/architecture/Architecture.md`：工程边界、运行、数据、安全、运维与容量。
- `docs/architecture/adr/ADR-0001` 至 `ADR-0004`：模块化单体、PostgreSQL 任务队列、双模型流水线、单机 Compose。
- `docs/design/Design-Spec.md`：与已确认原型一致的 Web 设计基线。
- `docs/delivery/Test-Plan.md` 与 `Release-Checklist.md`：独立验证和生产发布门禁。
- `docs/diagrams/`：系统上下文、用户流程、核心逻辑和状态模型。

## 锁定架构

- 前端：Vue 3、TypeScript、Vite 8、Node.js 24 LTS、pnpm。
- 后端：Python 3.13、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic。
- 数据与任务：PostgreSQL 18；Worker 使用 `FOR UPDATE SKIP LOCKED`。
- 模型：千问 `qwen3.7-plus` 非思考模式主写，DeepSeek `deepseek-v4-pro` 复核，`deepseek-v4-flash` 降级。
- 部署：单台 Linux 主机、Docker Compose、Caddy、API、Worker、PostgreSQL 和加密备份。
- V1 排除：微服务、Redis、向量数据库、自动发布、客户登录、多角色、支付、搜索 API、地图 API、云 OCR 和其他客户端。

## 自检结果

- 22 个 Markdown 文件的代码围栏数量平衡。
- PRD、接口契约、Plan、架构、设计、测试、发布与原型必需文件均存在。
- 65 个接口均包含请求、成功和至少一种错误响应。
- API 契约中无省略号、`TBD`、待定或后续占位。
- 阶段 C 决策文件中无供应商、模型、框架、数据库、存储或部署方案悬空。
- `.sdd/tmp` 只保留 `.gitkeep`；B2 临时视觉截图已移入 `.sdd/evidence/visual-research-2026-07-26/` 留作可追溯证据。
- Developer 尚未开始，不存在 Developer 自行验收。
- ECC Doctor 检查通过；阶段 C 状态为 `passed`，Architecture Gate 为 `passed`，Development Gate 保持 `pending`。

## 剩余门禁

- 产品负责人说“开始开发”后，Router 才能创建开发任务并进入多 Agent 开发。
- 真实模型联调需要产品负责人把 DeepSeek 与百炼 Key 注入本地安全配置。
- 云主机、域名、付费额度和生产部署仍需单独明确授权。
