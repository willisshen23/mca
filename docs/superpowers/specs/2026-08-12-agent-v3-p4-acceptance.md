# agent_v3 P4 验收记录：openJiuwen 版离线部署包

> 日期：2026-08-12
> 依据：`2026-08-12-agent-v3-p4-offline-packaging-design.md`
> 环境：macOS 宿主机 + Docker linux/amd64（构建 python:3.12-bookworm；验证 debian:buster-slim glibc 2.28 ≈ ky10 V10）
> 结论：通过

## 产物

- 包：`offline-v3/dist/activity-analysis-assistant-offline-20260812-074808.tar.gz`（262M）
- wheel 集：161 个 / 142M（`offline-v3/wheels`）；MANIFEST.sha256 随包
- 钉版例外（无 wheel 个案处理）：无（闭包一次通过）

## 阶段 1：断网安装验证（--network none）

| 检查 | 结果 |
|---|---|
| MANIFEST.sha256 | ✅ |
| pip --no-index 全量安装 | ✅ |
| import src.main | ✅ IMPORT_OK |

容器：`--network none debian:buster-slim`，阶段 1 耗时约 2 分 25 秒。

## 阶段 2：业务冒烟

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 健康检查 + deploy-offline.sh 无交互跑通 | ✅ | 从解压到服务就绪约 7 分钟 |
| 2 | 对话 + search_activities | ✅ | SMOKE-OK |
| 3 | 审批 approve（add_to_analysis_queue） | ✅ | analysis_queue=1 |
| 4 | generate_report 全流程 | ✅ | 7 个管线步骤帧成对，html_report 非空 |

阶段 2 耗时约 10 分 20 秒；全程 12 分 46 秒，输出 VERIFY-PASS。
证据日志：`/tmp/p4-verify-final.log`。

## 过程中发现并修复的缺陷

1. **verify.sh 两处 `docker run` 缺 `-i`**：heredoc 未送达容器 stdin，脚本空跑仍输出
   VERIFY-PASS（假阳性）。修复后重跑方取得上述真实证据（修复 commit `5d8f29c`）。
2. **start-offline.sh 缺 CA 信任库兜底**：openjiuwen 严格 SSL 校验走系统 CA，系统 CA
   不全的目标机上 LLM 调用全部 `CERTIFICATE_VERIFY_FAILED`。修复为 venv activate 后
   带守卫的 `SSL_CERT_FILE=certifi` 兜底（修复 commit `7800646`，用户裁决批准修改该
   文件）；同 commit 内 verify.sh 的 `LLM_*` 变量补 `export`。

## 部署警告（随版本发布）

1. 旧 `.env` 残留 `AGENT_V3_ENABLED` 会导致启动失败，部署前删除（沿用 P3 警告）。
2. ~~requirements-offline.txt 未包含 openjiuwen~~（P3 警告 #2，本阶段已闭环）。
3. 目标机若系统 CA 证书不全（最小化/定制 OS），`start-offline.sh` 已内置
   `SSL_CERT_FILE=certifi` 兜底，无需手工处理（见缺陷 #2 修复）。

## 补丁：前端静态目录错位修复（2026-08-12）

**根因**：应用唯一 StaticFiles 挂载点是 `backend/src/infrastructure/static`
（`backend/src/main.py`），而 `offline-v3/build.sh` 把 `frontend/dist` 拷到了
`$STAGE_DIR/backend/src/static`——该目录无人服务。

**影响**：初验包 `activity-analysis-assistant-offline-20260812-074808.tar.gz` 内两个目录
都有 index.html，实际服务的是 git 跟踪的 2026-07-10 旧前端（commit `1206ef8`），新前端
白打包。属初验盲区：原 smoke 只打 API，未断言前端内容。

**修复**（commit `1b876f6`）：

1. `build.sh`：前端产物改拷 `backend/src/infrastructure/static`（先 `rm -rf` 目标再
   `cp -a`，覆盖 git 跟踪的旧前端；不再动 `src/static`）。
2. `smoke.py`：健康检查后新增前端新鲜度断言——`GET /` 必须 200 且响应体包含
   `EXPECTED_ASSET`（哈希资产文件名）环境变量的值，未设置则跳过并打印提示。
3. `verify.sh`：阶段 2 docker run 前从宿主机 `frontend/dist/index.html` 提取
   `EXPECTED_ASSET` 并 **export**（首轮因未 export，`-e EXPECTED_ASSET` 读到空值，
   断言被跳过——重跑修复后取得真实证据）后随 `-e` 传入容器。

**新包**：`offline-v3/dist/activity-analysis-assistant-offline-20260812-090232.tar.gz`
（260M，wheels 161 个 / 143M）。包内 `backend/src/infrastructure/static/index.html`
引用 `assets/index-yk1Ld372.js`，与宿主机 `frontend/dist` 一致；包内不存在
`backend/src/static`。

**重验证据**（`bash offline-v3/verify.sh`，日志 `/tmp/p4-verify-fix.log`）：

```
[SMOKE-OK] 健康检查
[SMOKE-OK] 前端页面可访问且为最新构建
[SMOKE-OK] 对话 + search_activities 工具调用
[SMOKE-OK] 审批 approve 生效，analysis_queue=1 项
[SMOKE-OK] 报告生成（7 个管线步骤帧成对，html_report 非空）
SMOKE-PASS
VERIFY-PASS: .../activity-analysis-assistant-offline-20260812-090232.tar.gz
```

SMOKE-OK×5（新增前端一项）+ SMOKE-PASS + VERIFY-PASS，无 SMOKE-FAIL。包内资产核对：
`tar -xzOf <新包> activity-analysis-assistant/backend/src/infrastructure/static/index.html | grep -o 'assets/index-[^"]*\.js'`
输出 `assets/index-yk1Ld372.js`，与宿主机 `frontend/dist/index.html` 一致。
