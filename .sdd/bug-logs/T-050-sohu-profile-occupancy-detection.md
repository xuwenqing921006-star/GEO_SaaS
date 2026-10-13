# T-050 搜狐号登录窗口占用被误报为连接异常

## 现象

- 运营人员已在搜狐号独立登录窗口完成登录。
- 未关闭该窗口时点击“检测连接”，页面显示 `BrowserType.launch_persistent_context` 技术错误。

## 期望

- 登录窗口仍在使用同一浏览器 profile 时，不应显示连接异常或原始浏览器日志。
- 页面应提示“登录窗口仍在打开，请关闭窗口后再次检测连接”。
- 后台自动巡检遇到该状态时延后检测，不应把账号判定为失效。

## 根因

登录窗口和检测进程使用同一个持久化 profile。Chrome 检测到已有实例后，把目标页面转交给
现有窗口并让新启动的进程退出；Playwright返回“Target page, context or browser has been
closed / Opening in existing browser session”。原占用识别规则没有覆盖这类 Chrome 日志，
因此被存成了 `error`。

## 修复

- 将 `Opening in existing browser session` 纳入 profile 占用识别。
- 占用状态返回 `awaiting_login` 和可操作的中文提示，不再返回 `error`。
- 手动检测提示关闭登录窗口后重试；后台巡检遇到该状态继续延后，不改写有效会话。
- 旧的原始 Playwright 错误在 API 展示层继续被转换为简短用户提示。

## 验证

- 新增占用错误回归测试，修复前失败、修复后通过。
- 发布适配器、会话健康、每日巡检和发布前复检共 14 项定向测试通过。
- 本地页面复测已将搜狐账号从“检测异常 + 原始日志”改为“等待登录 + 关闭窗口后再次检测”，
  页面控制台无业务错误。
- 任务仍归属 T-046 开发中，不由 Developer 标记 PASS。
