# T-016 P1/P2 修复 — Reviewer 最终独立复核

- 日期：2026-07-28（Asia/Shanghai）
- 角色：Reviewer
- 对象：T-016 全站明亮视觉与弹窗体验重构最终修复
- 结论：**PASS**
- P0：0
- P1：0
- P2：0
- 约束：本轮仅覆盖 Reviewer 证据报告，未修改业务代码、业务数据、任务状态或生产环境。

## 最终结论

上轮报告的 P1 和 P2 均已关闭：

- 普通 `.modal-actions` 已统一采用 sticky 定位；在 1024×768 的原失败场景中，“新建客户”弹窗正文保持可滚动，取消与创建按钮同时保持在弹窗可视范围内。
- 新增真实 Chromium 回归，专门覆盖 1024×768 的普通长表单操作区。
- `expectBrightShell` 已移除错误的 `Promise<void>` 返回类型，独立严格 TypeScript 检查通过。
- T016 Chromium 当前 4/4 通过。

修复未改变后端 API、业务流程或数据结构，未发现新的安全、敏感信息、视觉一致性或兼容性问题。

## 上轮问题关闭情况

| 上轮问题 | 本轮状态 | 独立证据 |
| --- | --- | --- |
| P1-01：普通长表单底部操作区未固定，1024×768 首屏不可见 | **已关闭** | `bright-theme.css:521-532` 统一 sticky；真实服务复测操作区完全位于 dialog 内；新增 Chromium 回归通过。 |
| P2-01：T016 E2E 辅助函数错误声明为 `Promise<void>`，严格类型检查失败 | **已关闭** | `t016-ui-refresh.e2e.ts:12-39` 改为正确推断返回对象；独立 strict tsc 0 error。 |

## P1 修复复核

### 共享操作区实现

`frontend/src/bright-theme.css:521-532` 对以下两类现有操作区统一应用：

- `.modal-body > .modal-actions`
- `.modal-body > .client-form > .modal-actions`

关键属性：

- `position: sticky`
- `bottom: -24px`
- `z-index: 3`
- 半透明白色背景、顶部阴影与模糊效果

因此新建客户、编辑客户、离开确认、账户和修改密码等使用普通 `.modal-actions` 的弹窗，不再依赖每个业务弹窗单独添加 `.sticky-actions`。

### 原失败场景真实复测

Reviewer 在当前真实本地服务执行：

1. 视口设为 1024×768；
2. 打开客户工作台；
3. 点击“新建客户”；
4. 在正文未滚动的初始状态读取 dialog、body 和 actions 的实际布局。

结果：

| 项目 | 结果 |
| --- | --- |
| dialog | `top 45.34 / bottom 746.66 / height 701.32` |
| modal body | `clientHeight 634 / scrollHeight 732 / scrollTop 0` |
| actions | `top 672.19 / bottom 745.87` |
| actions 可见性 | **true** |
| computed position | `sticky` |
| computed bottom | `-24px` |
| 页面滚动锁 | `body overflow: hidden` |

正文确实超过可用高度并保持内部滚动，但操作区 `bottom 745.87` 没有超过 dialog `bottom 746.66`，取消和创建按钮均位于弹窗可视范围内。原 P1 已被真实关闭。

### 新增回归

`frontend/e2e/t016-ui-refresh.e2e.ts:133-165` 新增普通长表单回归：

- 使用 1024×768；
- 打开“新建客户”；
- 断言正文 `scrollHeight > clientHeight`；
- 断言 actions 上下边界均位于 dialog 内。

该用例与知识档案 `.sticky-actions` 用例相互独立，现已同时覆盖共享普通 footer 和业务特例。

## P2 修复复核

- `expectBrightShell` 不再声明 `Promise<void>`，返回值由 TypeScript 正确推断为包含：
  - `overflow`
  - `scrollWidth`
  - `clientWidth`
  - 明亮侧栏、主题令牌和图标统计
- 调用端读取上述属性与实际返回类型一致。
- Reviewer 独立执行：

```text
pnpm exec tsc --ignoreConfig --noEmit --target ES2023 --module ESNext \
  --moduleResolution Bundler --strict --skipLibCheck \
  e2e/t016-ui-refresh.e2e.ts
```

结果：**PASS，0 error**。

当前主 `tsconfig.json` 仍不包含 E2E，但本轮原始类型错误已经关闭；上述独立命令为该 E2E 文件提供了可复现的严格检查证据。

## 全站与弹窗回归确认

T016 Chromium 4 项全部通过：

1. 8 个 Web 工作区在 1440、1280、1024 宽度使用明亮侧栏且无页面级横向溢出；
2. “证据与授权”弹窗紧凑、结构化并支持键盘关闭；
3. 大型知识档案弹窗正文滚动时操作区保持可见；
4. 1024×768 普通新建客户长表单的操作区保持可见。

既有独立复核结论继续成立：

- Logo、当前导航、SVG 导航图标和主按钮使用蓝色；
- 已确认、成功和业务结果状态继续使用绿色；
- `ModalDialog` 保留 `role="dialog"`、`aria-modal`、标题关联、中文关闭名称、Escape 关闭、焦点循环、焦点恢复和页面滚动锁；
- “证据与授权”首屏仍同时展示事实、状态、主要操作和证据；
- `prefers-reduced-motion` 仍会关闭弹窗动画。

## 兼容、安全与范围

- CSS 修复仅影响现有标准弹窗 footer 的定位和视觉层级，没有修改表单提交、取消或关闭事件。
- 新增 E2E 仅操作 `VITE_USE_MOCK=true` 环境，没有生产或外部副作用。
- 未新增真实 API Key、Token、私钥、第三方凭据或浏览器明文密钥保存。
- 未修改后端接口、数据库、模型调用、认证权限或业务规则。
- 未执行生产部署。

## Reviewer 独立验证

| 检查 | 结果 |
| --- | --- |
| T016 E2E 文件严格 TypeScript 检查 | **PASS，0 error** |
| T016 ModalDialog 聚焦单元测试 | **PASS，1 file / 2 tests** |
| `pnpm format:check` | **PASS** |
| `pnpm lint` | **PASS** |
| `pnpm test:e2e:t016` | **PASS，Chromium 4/4** |
| 真实服务 1024×768 原 P1 场景 | **PASS** |

T016 E2E 首次启动时 5179 端口被另一项短时本地测试占用；未停止未知进程，端口释放后原命令直接重跑并 4/4 通过。该瞬时环境占用不属于产品缺陷。

## Reviewer 最终判定

**PASS：P0 0 / P1 0 / P2 0。**

T016 的 Reviewer 工程复核已经通过，可进入独立 Tester 验证及 Product Manager 最终视觉与业务接受；任务状态仍应由对应职责角色更新。
