# GitHub 仓库与协作

- 仓库：[xuwenqing921006-star/GEO_SaaS](https://github.com/xuwenqing921006-star/GEO_SaaS)。
- 可见性：私有；仓库所有者需要给接手同事开通访问权限。
- 主分支：`main`。
- 本次交付：普通独立工程的开发交接基线，包含代码、迁移、测试、文档和脱敏环境示例；不包含本机运行数据和第三方登录会话。
- 仓库原有初始化 README 提交作为历史保留；项目代码在其后提交，不导入上层开发工具仓库。

## 同事接手

拥有仓库权限后，使用自己的 GitHub 身份克隆：

```powershell
git clone https://github.com/xuwenqing921006-star/GEO_SaaS.git
Set-Location GEO_SaaS
```

按 [README](../../README.md) 安装与启动，阅读 [交接说明](HANDOFF.md) 和 [未完成任务](OPEN-TASKS.md)。不需要 ECC_V2；团队也可以自行选择将它作为开发工具。

每项变更可在独立分支工作，通过 Pull Request 合并回主分支，例如：

```powershell
git switch main
git pull --ff-only
git switch -c feature/describe-your-change
```

分支命名与审查规则由团队确定。提交时说明业务变化、验证结果和剩余限制，不把模拟结果当成真实平台发布验收。

## 数据与权限

负责人账号需要在新环境初始化；模型密钥、现有客户数据与文件存储另行通过受控渠道交接，详情见交接说明。GitHub 访问权限与系统负责人账号互相独立；获得源码并不会获得原环境的登录权限。

该仓库不是生产部署。历史业务任务仍有 38 项进行中、1 项失败；交接文档通过检查不等于所有功能已验收。
