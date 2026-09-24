# Test Center Guide · TOS 7 Docker 应用

Test Center 测试管理平台的**离线上手指南**与**部署助手**，封装为符合 TOS 7 规范的
Docker 应用（提交格式 `<appid>.tar.gz`，归档根层恰好 4 个文件）。

- **应用 ID**：`test-center-guide-docker`
- **应用类型**：`docker`（单容器）
- **打开方式**：浏览器外部打开（`open_path: true`）
- **镜像**：`whiteelm/test-center-guide:<version>`（Docker Hub 公共仓库）
- **规范依据**：《TOS 7 Application Development Guide》第 9 章 + `TOS社区应用上架规则.md`

## 这是什么

一个只做一件事的静态站点：把 Test Center 的**功能总览**、**部署步骤**讲清楚，
并提供一个**纯前端的部署助手**——填几个参数就能生成本环境可用的 `.env` 与整套命令。

镜像基于 Docker Hub 官方 `nginx:*-alpine` 构建，站点内容为本项目自有，不连接任何
外部服务、不收集任何数据（详见 `PRIVACY.md`）。

## 应用信息

| 项 | 值 |
|----|----|
| 应用 ID | `test-center-guide-docker` |
| 显示名（中） | Test Center 上手指南 |
| 显示名（英） | Test Center Guide |
| 版本 | `1.0.0`（改版见 `versions.env`） |
| 发布者 | Ryan |
| 分类 | `Development_Tools`、`Utilities` |
| 依赖 | `DockerEngine` |
| 平台 | `x86_64`（ARM 机型需另出一份 `aarch64` 包） |
| 宿主机端口 | `19013`（容器内 `8080`） |
| 运行用户 | `1000:1000`（非 root） |

## Permissions

| 权限 / 能力 | 用途 | 是否为最小必要 |
|------------|------|---------------|
| Docker 端口映射（宿主机 `19013` → 容器 `8080`） | 让 TOS 桌面与浏览器能打开指南页面 | 是，唯一对外端口 |
| 写 `/Volume*/DockerAppData/test-center-guide-docker/logs` | 保存 nginx 访问日志（唯一的落盘数据） | 是，用于运行排查 |
| `cap_drop: ALL` + 白名单 `CHOWN`/`DAC_OVERRIDE`/`FOWNER`/`SETGID`/`SETUID` | 让 nginx 以非 root 启动并读写自身目录 | 是，能力集已从默认 41 项收窄 |
| `no-new-privileges: true` | 禁止进程提权 | 安全加固项 |
| 网络访问 | **不需要**：不发起任何对外请求 | — |
| 挂载宿主机敏感目录 / `privileged` / `network_mode: host` | **均未使用** | — |

## Ports

| 端口 | 协议 | 用途 | 是否对外 |
|------|------|------|---------|
| `19013` | TCP/HTTP | 指南站点（宿主机端口，可在安装后调整） | 是 |
| `8080` | TCP/HTTP | 容器内 nginx 监听端口（非特权端口，非 root 运行的前提） | 容器内 |

未使用任何系统保留端口（22 / 80 / 443 / 445 / 3306 / 5050 / 5432 / 6379 / 8181 / 8443）。

## 目录结构

```
TOS_test-center-guide-docker/          # = GitHub 仓库根目录
├── config.ini                          ★ 提交包含的 4 个文件之一
├── test-center-guide-docker.lang       ★ 多语言（14 种）
├── test-center-guide-docker.svg        ★ 图标（透明背景 + viewBox）
├── docker-compose.yml                  ★ 编排模板，@@VAR@@ 由打包脚本替换
├── versions.env                        # 版本 / 命名空间 / 端口（改版入口）
├── Dockerfile                          # 镜像构建（官方 nginx:alpine → 非 root）
├── nginx.conf                          # 容器内 nginx 配置（监听 8080）
├── web/                                # 站点源文件（打进镜像）
│   ├── index.html / features.html / deploy.html / generator.html / faq.html
│   └── assets/{style.css, app.js, i18n.js, favicon.svg}
├── scripts/
│   ├── build-image.sh                  # 构建 + 本地自测 + 推 Docker Hub
│   ├── build-package.py                # 合规自检 + 出 4 文件包 + sha256
│   └── verify-images.py                # 提交前在线核对镜像 tag
├── .github/workflows/release.yml       # CI：构建 → Trivy → 推送 → 出包 → Release
├── LICENSE / NOTICE / PRIVACY.md / README.md
```

## 构建与发布

镜像必须推到 Docker Hub（TOS 只接受 Docker Hub 镜像），而**开发机通常没有 Docker、
也连不上 hub.docker.com**，所以有两条路，任选：

**A. 交给 CI（推荐）** —— 推一个 tag 即可，CI 会构建、扫描、推镜像、出包、发 Release：

```bash
git tag 1.0.0 && git push origin 1.0.0
```

需先在仓库 `Settings → Secrets and variables → Actions` 配置：

| Secret | 说明 |
|--------|------|
| `DOCKERHUB_USERNAME` | Docker Hub 用户名（`whiteelm`） |
| `DOCKERHUB_TOKEN` | Docker Hub Access Token，权限选 **Read & Write**（不是登录密码） |

**B. 在 NAS 上手动跑**（TOS 装好 Docker Engine 后，用 Terminal）：

```bash
bash scripts/build-image.sh          # 构建 + 本地自测（非 root 起得来 / healthz 通）+ 推送 + 出包
bash scripts/build-image.sh --no-push   # 只构建自测
```

出包与自检（任何带 Python 3 的机器都能跑，零第三方依赖）：

```bash
python scripts/build-package.py                  # 全量自检 + 出包
python scripts/build-package.py --skip-verify    # 离线环境跳过镜像在线核对
```

产物：`dist/test-center-guide-docker.tar.gz` + `.tar.gz.sha256`

## 提交上架清单

- [ ] 两个 Secret 已配置，镜像已推到 Docker Hub（`whiteelm/test-center-guide:1.0.0`）
- [ ] Release 资产齐全：`.tar.gz` + `.tar.gz.sha256` + `trivy-report.txt`
- [ ] `config.ini` 的 `version` = `versions.env` 的 `TOS_VERSION` = Release tag（三处一致）
- [ ] 平台注册填：Application ID `test-center-guide-docker`、Package Type **Docker**、
      版本 `1.0.0`、Repository URL `https://github.com/RyanYang163/test-center-guide-docker`
- [ ] 设备上确认 `19013` 端口未被占用
- [ ] 备注栏写清本应用的用途（静态指南 + 部署助手），避免被判「功能不完整」

## 基础镜像与漏洞门禁（改版本前必读）

CI 在**推镜像之前**会先本地构建、用 Trivy 扫一遍：**「存在官方修复」的 HIGH/CRITICAL 必须为 0**，
否则流水线停在那一步、镜像不会推出去（宁可没有，也不推脏镜像）。

⚠️ **基础镜像 tag 是会腐烂的**：镜像不在本地，CI 每次按 tag 重新拉；而 Alpine 基础包与 nginx
本身一直在出 CVE 和修复版。实测记录：

| 日期 | 钉的 tag | 结果 |
|---|---|---|
| 2026-09-24 | `nginx:1.27-alpine`（2024 年的 minor） | ❌ **40 个可修复 HIGH/CRITICAL**，门禁拦下 |
| 2026-09-24 | `nginx:1.31.6-alpine`（当天刚构建） | ⚠️ 仍差 1 个：镜像里的 `libexpat 2.8.4-r0` 有可修复 HIGH（仓库里已是 2.8.5-r0）|
| 2026-09-24 | 同上 + **构建时 `apk upgrade --no-cache`** | ✅ 结果见 Release 附带的 `trivy-report.txt` |

> **教训**：`alpine` 系基础镜像**只在 Alpine 发版时重建**，所以镜像里的包会滞后于 Alpine 仓库 ——
> 连「当天刚构建」的 tag 都可能差一两个包。因此在 Dockerfile 里加 `RUN apk upgrade --no-cache`，
> 每次构建都取仓库当前版本：仓库修了就自动跟上，仓库还没修的 trivy 也不计入（`--ignore-unfixed`）。**别删这一行。**

**换版本的步骤**：

1. 改 `Dockerfile` 的 `FROM` 与 `versions.env` 的 `NGINX_IMAGE` —— **两处必须一致**
2. **升版本号**（同一版本号的 Release 不允许覆盖），重新打 tag 推上去
3. 本机查不到候选版本（`hub.docker.com` 四个端点全不可达、代理也不放行 registry）——
   扫描失败时 CI 会用 `::notice::` 把线上较新的 alpine 标签回传，
   **读注解而不是下日志**（日志有 302 跳转到 `objects.githubusercontent.com`，本机会断）：
   `python 101-临时目录\watch-ci-run.py RyanYang163/test-center-guide-docker workflow_dispatch`

## 改站点内容时注意（i18n 约定）

站点是**中英双语**的，右上角可切换。机制刻意做成单向，避免两份中文互相漂移：

| 语言 | 来源 |
|------|------|
| 中文 | **页面 HTML 里的原文**（唯一来源）；切回中文时由 `app.js` 还原原始文本 |
| 英文 | `web/assets/i18n.js` 的字典（只有 `en`） |

四条属性对应四类内容，加新文案时按类型挂上去：

| 属性 | 用在哪 | 例子 |
|------|--------|------|
| `data-i18n` | 纯文本元素（标题、段落、按钮） | `<h1 data-i18n="index.title">Test Center 上手指南</h1>` |
| `data-i18n-html` | 块级内容（表格、列表、含 `<code>`/`<strong>` 的段落） | `<table data-i18n-html="index.stack.table">` |
| `data-i18n-code` | 命令块（只翻 `#` 注释，命令本体不动） | `<pre data-i18n-code="deploy.verify.code">` |
| `data-i18n-ph` | 输入框 placeholder | `<input data-i18n-ph="gen.ph.adminPassword">` |

**加了中文但忘了挂属性 → `build-package.py` 会直接报 ERROR**（有覆盖率检查，
扫出「没接字典的中文」，因而不可能悄悄漏译）。部署助手的命令注释也是双语的，
由 `app.js` 的 `L(key, 中文默认值)` 取词。

## 已知限制

- **Docker 应用不支持平台内升级**：官方后端对 Docker 应用直接返回
  `update not supported for docker apps`，用户需卸载重装（数据目录会保留）。
- **镜像是个人账号下的镜像**：审核项 H14 要求镜像来自 Docker Hub（已满足），
  但 §9.4 另有一条「拉取量少、无文档的个人镜像」会被拒的风险 ——
  缓解方式是本仓库与 Docker Hub 仓库页都写全说明、许可证与隐私政策。
- **不内置上游的私有仓库地址与体验账号**：那些属于项目方，且体验账号会变动；
  页面只说「向项目方索取」。默认管理员口径（部署工具建 `test` / `Admin123`、
  手动部署用第 7 步自填的账号）已在部署指南与常见问题里写明。

## License

本项目采用 **MIT 许可证**，全文见 [LICENSE](./LICENSE)。
第三方组件与引用说明见 [NOTICE](./NOTICE)。隐私政策见 [PRIVACY.md](./PRIVACY.md)。

> 本仓库介绍的是 Test Center 测试管理平台，但**不包含**该平台的任何源代码或
> 二进制，也不内置其仓库地址与凭据；页面内容为依据公开部署流程自行撰写的说明。
