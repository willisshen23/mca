# 《功能说明书》编写实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 依据 `docs/superpowers/specs/2026-07-27-functional-spec-design.md`，产出面向行内交付验收的《功能说明书》（Markdown 源 + Word 交付版）。

**Architecture:** 先核实功能点清单（以代码实际交付为准）→ 搭建 Pandoc 工具链 → 启动三服务（backend:8000 / frontend:3000 / mock:8005）用 Playwright 截真实界面图 → 按模块分章编写（每章一个独立 md 文件）→ 组装、校对、转 Word。

**Tech Stack:** Markdown、Pandoc（+ reference.docx）、Playwright MCP（截图）、Vue 3 前端 / FastAPI 后端 / mock 服务（截图环境）。

## Global Constraints

- 只写**已实现且在验收环境可见**的功能，不写规划/废弃功能（v1 相关内容一律不写）；
- 功能点编号规则：`F-<模块码>-<两位序号>`，模块码：`CHAT / ACT / RPT / HITL / SKILL / TPL / HIST / SYS`；
- 每个功能点必须包含六要素：功能编号、功能描述、界面截图、操作步骤、输入/输出（表格）、业务规则与约束；
- 截图统一存 `docs/功能说明书/images/`，命名 `fig-<章号>-<两位序号>-<英文slug>.png`（如 `fig-03-01-chat-main.png`），正文引用相对路径 `images/xxx.png`，图题格式"图 <章号>-<序号> <名称>"；
- 每章一个源文件：`docs/功能说明书/chapters/<两位章号>-<英文名>.md`，最终组装为 `docs/功能说明书/功能说明书.md`；
- 措辞正式、书面语，面向验收；不出现"mock""开发态"等内部措辞（截图来源可以是 mock 环境，但正文不提及）；
- 不做"功能点验收对照表"附录，不做"外部接口说明"章节（用户已确认）；
- 每个 Task 完成后单独 commit。

---

### Task 1: 功能点清单核实

**Files:**
- Create: `docs/功能说明书/功能点清单.md`（内部工作文件，不进入交付 Word）
- Read: `docs/需求说明书.md`（功能需求章节）
- Read: `backend/src/api/routers/`（14 个路由文件，核实后端能力）
- Read: `frontend/src/views/`（11 个视图，核实界面功能）
- Read: `frontend/src/config/features.js`（特性开关，已知 `SHOW_PDF_EXPORT = false`）
- Read: `frontend/src/router/index.js`（页面路由表）

**Interfaces:**
- Consumes: 设计文档 `docs/superpowers/specs/2026-07-27-functional-spec-design.md` 第 2 节（章节结构）与第 3 节（模块码约定）
- Produces: `功能点清单.md`，按 8 个模块（CHAT/ACT/RPT/HITL/SKILL/TPL/HIST/SYS）列出全部功能点编号与名称——后续 Task 6–13 以此清单为各自章节的权威功能点范围

- [ ] **Step 1: 通读需求说明书功能需求章节**

提取需求说明书中的功能点列表，作为清单初稿骨架。

- [ ] **Step 2: 对照代码核实每个功能点**

逐个核实：功能点在当前代码中是否已实现、在验收环境（生产构建）是否可见。重点核实以下疑点并记录结论：
- `SHOW_PDF_EXPORT = false`：报告导出 UI 是否可见？导出功能点如何表述（可见则正常写；不可见则核实后端导出能力是否在报告页其他入口暴露，以验收环境实际可见为准）；
- `HomeView`（/management）与 `SourceConfigView`（/analysis/:type/source）是否为当前有效页面，归属哪个章节；
- 报告版本管理（report_versions）在前端哪个视图可见。

- [ ] **Step 3: 写功能点清单**

按模块分组列出全部功能点，格式：

```markdown
## CHAT 对话交互
| 编号 | 功能点 | 来源（需求说明书章节/代码文件） | 验收环境可见 |
|---|---|---|---|
| F-CHAT-01 | 自然语言提问与流式应答 | 需求 3.x；agent_v2.py | 是 |
```

- [ ] **Step 4: 自检**

对照设计文档第 2 节目录：3–10 章每个小节都有对应功能点编号，无遗漏、无多余。

- [ ] **Step 5: Commit**

```bash
git add docs/功能说明书/功能点清单.md
git commit -m "功能说明书：功能点清单核实"
```

---

### Task 2: 文档目录与 Word 工具链

**Files:**
- Create: `docs/功能说明书/chapters/`（目录）、`docs/功能说明书/images/`（目录）
- Create: `docs/功能说明书/reference.docx`（Pandoc 样式模板）
- Create: `docs/功能说明书/build.sh`（组装 + 转 Word 脚本）

**Interfaces:**
- Consumes: 无
- Produces: `build.sh`，用法 `bash docs/功能说明书/build.sh`，输入 `chapters/*.md`，输出 `功能说明书.md` 与 `功能说明书.docx`——Task 14 依赖它产出交付物

- [ ] **Step 1: 安装 Pandoc**

```bash
brew install pandoc
pandoc --version   # 期望输出 3.x
```

- [ ] **Step 2: 建目录并生成 reference.docx**

```bash
mkdir -p docs/功能说明书/chapters docs/功能说明书/images
cd docs/功能说明书 && pandoc -o reference.docx --print-default-data-file reference.docx
```

- [ ] **Step 3: 写 build.sh**

```bash
#!/usr/bin/env bash
# 用法：bash docs/功能说明书/build.sh
# 按章号顺序拼接 chapters/*.md → 功能说明书.md，并转 docx（自动目录）
set -euo pipefail
cd "$(dirname "$0")"
cat chapters/*.md > 功能说明书.md
pandoc 功能说明书.md \
  -o 功能说明书.docx \
  --reference-doc=reference.docx \
  --toc --toc-depth=3 \
  -M title="活动分析助手 功能说明书"
echo "已生成 功能说明书.md / 功能说明书.docx"
```

- [ ] **Step 4: 验证工具链**

写一个临时 `chapters/00-test.md`（含标题、表格、图片引用占位），运行 `bash docs/功能说明书/build.sh`，确认两个产物生成且无报错，然后删除 `00-test.md` 与产物。

- [ ] **Step 5: Commit**

```bash
git add docs/功能说明书/build.sh docs/功能说明书/reference.docx
git commit -m "功能说明书：文档目录与 Pandoc 工具链"
```

---

### Task 3: 启动截图环境

**Files:**
- 无新文件；启动 3 个服务（后台进程）

**Interfaces:**
- Consumes: 无
- Produces: 可访问的 `http://localhost:3000`（前端，/api 代理到 8000）——Task 4 截图依赖

- [ ] **Step 1: 启动 mock 服务**

```bash
cd mock && uvicorn app:app --port 8005
```

后台运行（`run_in_background`）。验证：`curl -s http://localhost:8005/docs -o /dev/null -w "%{http_code}"` 期望 `200`。

- [ ] **Step 2: 启动后端**

```bash
cd backend && python -m src.main
```

后台运行。验证：`curl -s http://localhost:8000/health` 期望返回正常 JSON。

- [ ] **Step 3: 启动前端**

```bash
cd frontend && npm run dev
```

后台运行。验证：`curl -s http://localhost:3000 -o /dev/null -w "%{http_code}"` 期望 `200`。

- [ ] **Step 4: 浏览器冒烟**

用 Playwright MCP `browser_navigate` 打开 `http://localhost:3000/chat-ui`，`browser_snapshot` 确认对话界面渲染正常。若前端特性要求 URL 参数（`userId`/`orgNo`/`channel`），用 `http://localhost:3000/chat-ui?userId=demo&orgNo=0000&channel=AILMIS`。

---

### Task 4: 界面截图采集

**Files:**
- Create: `docs/功能说明书/images/fig-*.png`（约 20 张）

**Interfaces:**
- Consumes: Task 3 的运行环境；Task 1 的功能点清单（决定截图覆盖范围）
- Produces: 以下截图文件——Task 6–13 写章节时引用这些确切文件名

**必截清单**（命名即文件名，缺图会导致对应章节无法完成）：

| 文件 | 内容 |
|---|---|
| `fig-03-01-chat-main.png` | 对话主界面（含侧边栏） |
| `fig-03-02-quick-prompts.png` | 快捷提问 |
| `fig-03-03-streaming.png` | 流式应答进行中 |
| `fig-03-04-perspective.png` | 分析视角切换入口/选项 |
| `fig-03-05-upload.png` | 文件上传（CSV/Excel）入口或已上传状态 |
| `fig-03-06-conversations.png` | 会话管理（列表/重命名/删除） |
| `fig-04-01-activity-search.png` | 活动搜索结果卡片 |
| `fig-04-02-activity-detail.png` | 活动详情 |
| `fig-04-03-queue.png` | 分析队列 |
| `fig-05-01-report-preview.png` | 报告预览（含图表） |
| `fig-05-02-report-versions.png` | 报告版本 |
| `fig-05-03-report-export.png` | 报告导出/下载入口（以 Task 1 核实结论为准；若 UI 不可见则改为报告下载按钮截图） |
| `fig-06-01-approval-card.png` | HITL 审批卡片（待审批状态） |
| `fig-07-01-skill-mgmt.png` | 技能管理列表 |
| `fig-07-02-skill-composer.png` | 技能编排画布 |
| `fig-08-01-templates.png` | 活动分析模板管理 |
| `fig-09-01-history.png` | 历史会话 |
| `fig-09-02-conversation-logs.png` | 对话审计日志 |
| `fig-09-03-logs.png` | 服务日志查看 |
| `fig-10-01-settings.png` | 系统设置/环境配置 |

- [ ] **Step 1: 静态页面截图**

对管理类页面（/skills、/analysis/compose、/templates、/history、/conversation-logs、/logs、/settings）逐页用 Playwright MCP `browser_navigate` + `browser_take_screenshot`（`scale: "css"`，`type: "jpeg"` 或 `png`）截图，按上表命名保存到 `docs/功能说明书/images/`。

- [ ] **Step 2: 对话界面截图**

在 /chat-ui 截图主界面、快捷提问、视角切换、文件上传入口、会话管理侧边栏。

- [ ] **Step 3: 交互态截图（需 LLM 可用）**

发送一条查询类提问（如"查询最近的营销活动"）截流式应答与活动结果卡片；触发一次写操作（如"把该活动加入分析队列"）截审批卡片；生成一份报告后截报告预览、版本、导出/下载。

若 LLM 不可用：在 `docs/功能说明书/功能点清单.md` 末尾记录缺失截图清单，对应章节先用文字描述并留图片占位（`![]()` 不写路径会破坏构建，应写“图 X-X 待补”文字段落替代），并在 commit message 中注明。

- [ ] **Step 4: 核对**

`ls docs/功能说明书/images/` 对照必截清单逐张确认存在且内容正确（Playwright `browser_take_screenshot` 后可 Read 图片目检）。

- [ ] **Step 5: Commit**

```bash
git add docs/功能说明书/images/
git commit -m "功能说明书：界面截图采集"
```

---

### Task 5: 第 1–2 章（引言、系统功能总览）

**Files:**
- Create: `docs/功能说明书/chapters/01-introduction.md`
- Create: `docs/功能说明书/chapters/02-overview.md`

**Interfaces:**
- Consumes: 设计文档第 2 节（1.x/2.x 小节范围）；`docs/需求说明书.md`（背景、术语表、架构图——可复用改写）
- Produces: 章节源文件；功能结构图与业务流程图的最终表述（后续章节不再重复）

- [ ] **Step 1: 写第 1 章**

小节：1.1 编写目的（说明本文档面向验收、描述系统实际功能与使用方法，与需求说明书定位区分）、1.2 系统概述（一段背景 + 架构简图，复用需求说明书架构图并核对与当前实现一致）、1.3 用户角色（业务分析人员、系统管理员，表格：角色/职责/主要使用章节）、1.4 参考文档（需求说明书、部署手册）、1.5 术语定义（复用需求说明书术语表，核对无 v1 残留术语）。

- [ ] **Step 2: 写第 2 章**

小节：2.1 功能结构图（用代码块画文字功能树，覆盖 Task 1 清单全部模块，不写功能点编号只到功能点名称层级）、2.2 典型业务流程（进入系统 → 查询活动 → 组建分析队列（审批）→ 生成报告 → 多轮修改（审批）→ 导出/下载，用编号步骤 + 每步注明对应章节号）、2.3 运行环境（支持的浏览器、部署形态一句话并指向部署手册）。

- [ ] **Step 3: 自检**

功能树与 Task 1 清单逐模块比对一致；全文无"mock/v1/开发态"字样。

- [ ] **Step 4: Commit**

```bash
git add docs/功能说明书/chapters/01-introduction.md docs/功能说明书/chapters/02-overview.md
git commit -m "功能说明书：第 1-2 章"
```

---

### Task 6: 第 3 章（对话交互功能）

**Files:**
- Create: `docs/功能说明书/chapters/03-chat.md`

**Interfaces:**
- Consumes: Task 1 清单 CHAT 模块功能点；Task 4 截图 `fig-03-*.png`；六要素模板（Global Constraints）
- Produces: 无（末章）

- [ ] **Step 1: 通读实现代码**

Read `frontend/src/views/UiChatView.vue` 与 `backend/src/api/routers/agent_v2.py`、`conversations.py`，核实每个功能点的实际行为（尤其是业务规则：同一会话同时仅一个运行中任务、取消语义、会话持久化）。

- [ ] **Step 2: 按六要素逐功能点编写**

覆盖 Task 1 清单 CHAT 模块全部功能点（预计：自然语言提问与流式应答、快捷提问、多轮对话与上下文、分析视角切换、文件上传、任务取消、会话管理，以清单为准）。每个功能点严格六要素，截图引用 Task 4 的实际文件名。

- [ ] **Step 3: 自检**

`grep -c "^#### F-CHAT" docs/功能说明书/chapters/03-chat.md` 与清单 CHAT 条目数一致；每个功能点下都有 `](images/fig-03-` 图片引用且文件存在。

- [ ] **Step 4: Commit**

```bash
git add docs/功能说明书/chapters/03-chat.md
git commit -m "功能说明书：第 3 章 对话交互"
```

---

### Task 7: 第 4 章（营销活动查询与分析队列）

**Files:**
- Create: `docs/功能说明书/chapters/04-activities.md`

**Interfaces:**
- Consumes: Task 1 清单 ACT 模块；截图 `fig-04-*.png`；实现参考 `backend/src/agent_v2/tools/`（search_activities / get_activity_detail / add_to_analysis_queue / remove_from_analysis_queue / update_analysis_config）
- Produces: 无

- [ ] **Step 1: 通读实现代码**（上述工具文件，核实搜索条件、队列约束、分析配置项的实际行为）
- [ ] **Step 2: 按六要素逐功能点编写**（活动搜索、活动详情、加入/移出分析队列、分析配置调整；涉及审批的功能点在"业务规则与约束"中注明"该操作需人工审批，详见第 6 章"）
- [ ] **Step 3: 自检**（编号数与清单一致；图片引用存在）
- [ ] **Step 4: Commit**

```bash
git add docs/功能说明书/chapters/04-activities.md
git commit -m "功能说明书：第 4 章 活动与分析队列"
```

---

### Task 8: 第 5 章（报告功能）

**Files:**
- Create: `docs/功能说明书/chapters/05-reports.md`

**Interfaces:**
- Consumes: Task 1 清单 RPT 模块；截图 `fig-05-*.png`；实现参考 `backend/src/api/routers/reports.py`、`frontend/src/views/ReportView.vue`、`backend/src/report_pipeline/`
- Produces: 无

- [ ] **Step 1: 通读实现代码**（重点核实：报告生成的用户可见行为——不写管线内部节点细节；版本链的用户可见表现；导出格式以 Task 1 核实结论为准）
- [ ] **Step 2: 按六要素逐功能点编写**（报告生成、报告预览与图表、报告多轮修改与版本管理、报告导出、报告下载，以清单为准）
- [ ] **Step 3: 自检**（同上）
- [ ] **Step 4: Commit**

```bash
git add docs/功能说明书/chapters/05-reports.md
git commit -m "功能说明书：第 5 章 报告功能"
```

---

### Task 9: 第 6 章（HITL 人工审批）

**Files:**
- Create: `docs/功能说明书/chapters/06-hitl.md`

**Interfaces:**
- Consumes: Task 1 清单 HITL 模块；截图 `fig-06-01-approval-card.png`；实现参考 `backend/src/agent_v2/agent_factory.py`（interrupt_on 配置）、`runtime.py`（resume）、前端审批卡片组件
- Produces: 无

- [ ] **Step 1: 通读实现代码**（核实：哪些操作触发审批、审批可选动作 approve/edit/reject 的用户语义、刷新后恢复的实际表现）
- [ ] **Step 2: 按六要素编写**（审批触发机制用"功能描述+业务规则"方式写，此功能点无独立操作步骤可写"被动触发，无需操作"；审批卡片操作、刷新恢复按正常六要素）
- [ ] **Step 3: 自检**（同上）
- [ ] **Step 4: Commit**

```bash
git add docs/功能说明书/chapters/06-hitl.md
git commit -m "功能说明书：第 6 章 HITL 审批"
```

---

### Task 10: 第 7 章（技能管理）

**Files:**
- Create: `docs/功能说明书/chapters/07-skills.md`

**Interfaces:**
- Consumes: Task 1 清单 SKILL 模块；截图 `fig-07-*.png`；实现参考 `frontend/src/views/SkillManagementView.vue`、`SkillComposerView.vue`、`backend/src/api/routers/skills.py`
- Produces: 无

- [ ] **Step 1: 通读实现代码**
- [ ] **Step 2: 按六要素逐功能点编写**（技能清单与分类、技能编排画布、技能新增/编辑/删除，以清单为准）
- [ ] **Step 3: 自检**（同上）
- [ ] **Step 4: Commit**

```bash
git add docs/功能说明书/chapters/07-skills.md
git commit -m "功能说明书：第 7 章 技能管理"
```

---

### Task 11: 第 8 章（模板与提示词管理）

**Files:**
- Create: `docs/功能说明书/chapters/08-templates.md`

**Interfaces:**
- Consumes: Task 1 清单 TPL 模块；截图 `fig-08-01-templates.png`；实现参考 `frontend/src/views/TemplateView.vue`、`backend/src/api/routers/activity_templates.py`、`system_prompts.py`、`quick_prompts.py`
- Produces: 无

- [ ] **Step 1: 通读实现代码**
- [ ] **Step 2: 按六要素逐功能点编写**（活动分析模板管理、System Prompt 管理、快捷提问管理，以清单为准；若 System Prompt / 快捷提问无独立管理界面而是内嵌在设置页，在 Step 1 核实后按实际界面归属编写）
- [ ] **Step 3: 自检**（同上）
- [ ] **Step 4: Commit**

```bash
git add docs/功能说明书/chapters/08-templates.md
git commit -m "功能说明书：第 8 章 模板与提示词"
```

---

### Task 12: 第 9 章（历史与日志）

**Files:**
- Create: `docs/功能说明书/chapters/09-history-logs.md`

**Interfaces:**
- Consumes: Task 1 清单 HIST 模块；截图 `fig-09-*.png`；实现参考 `frontend/src/views/HistoryView.vue`、`ConversationLogsView.vue`、`LogsView.vue`、`backend/src/api/routers/agent_run_history.py`、`conversation_logs.py`、`logs.py`
- Produces: 无

- [ ] **Step 1: 通读实现代码**
- [ ] **Step 2: 按六要素逐功能点编写**（历史会话与报告版本、对话审计日志、报告运行历史、服务日志查看/下载，以清单为准）
- [ ] **Step 3: 自检**（同上）
- [ ] **Step 4: Commit**

```bash
git add docs/功能说明书/chapters/09-history-logs.md
git commit -m "功能说明书：第 9 章 历史与日志"
```

---

### Task 13: 第 10 章（系统管理）+ 附录 A

**Files:**
- Create: `docs/功能说明书/chapters/10-system.md`
- Create: `docs/功能说明书/chapters/11-appendix-a.md`

**Interfaces:**
- Consumes: Task 1 清单 SYS 模块；截图 `fig-10-01-settings.png`；实现参考 `frontend/src/views/SettingsView.vue`、`backend/src/api/routers/env_config.py`
- Produces: 无

- [ ] **Step 1: 通读实现代码**（核实环境配置可改项、重启行为、特性开关的用户可见性；附录素材：收集各功能点编写过程中遇到的错误提示/异常场景）
- [ ] **Step 2: 按六要素逐功能点编写第 10 章**（环境配置查看/修改与重启、健康检查等，以清单为准）
- [ ] **Step 3: 写附录 A**（错误提示与异常场景一览，表格：场景 / 系统表现 / 处理方式，素材来自 Task 6–13 各章"业务规则与约束"中涉及的异常分支汇总，至少覆盖：LLM 服务不可用、写操作被拒绝、任务取消、上传文件格式不支持、报告生成失败）
- [ ] **Step 4: 自检**（同上）
- [ ] **Step 5: Commit**

```bash
git add docs/功能说明书/chapters/10-system.md docs/功能说明书/chapters/11-appendix-a.md
git commit -m "功能说明书：第 10 章与附录 A"
```

---

### Task 14: 组装、校对与 Word 产出

**Files:**
- Create: `docs/功能说明书/功能说明书.md`、`docs/功能说明书/功能说明书.docx`
- Modify: 各章节文件（校对修正）

**Interfaces:**
- Consumes: 全部章节文件、Task 2 的 `build.sh`、Task 1 的功能点清单
- Produces: 最终交付物

- [ ] **Step 1: 补封面与修订记录**

在 `chapters/01-introduction.md` 开头插入封面信息块（系统名称、文档版本 V1.0、编写日期、编写/审核/批准栏）与修订记录表。

- [ ] **Step 2: 全书一致性校对**

逐条核对：
- `grep -oh "F-[A-Z]*-[0-9]*" docs/功能说明书/chapters/*.md | sort -u` 与 Task 1 清单编号集合完全一致；
- 图片引用路径全部存在：`grep -oh "images/[^)]*" docs/功能说明书/chapters/*.md | sort -u`，每个文件 `ls` 确认；
- 图编号连续无重复；章节间交叉引用（"详见第 X 章"）正确；
- 全文无"mock""v1""开发态""TODO"字样：`grep -rn "mock\|TODO\|开发态" docs/功能说明书/chapters/`（图片文件名除外）。

- [ ] **Step 3: 构建**

```bash
bash docs/功能说明书/build.sh
```

确认生成 `功能说明书.md` 与 `功能说明书.docx`。

- [ ] **Step 4: Word 目检**

打开 `功能说明书.docx` 检查：封面、自动目录、章节编号、表格与图片渲染正常。若样式需调整，修改 `reference.docx` 后重新构建。

- [ ] **Step 5: Commit**

```bash
git add docs/功能说明书/
git commit -m "功能说明书：全书组装与 Word 产出"
```

---

## Self-Review 记录

- **Spec coverage**：设计文档第 2 节全部章节（1–10 章 + 附录 A）→ Task 5–13 全覆盖；第 3 节六要素模板 → Global Constraints + 各章 Step；第 4 节流程（清单核实/截图/编写/转换/校对）→ Task 1/4/6–13/2+14/14；第 5 节产出物 → Task 14。已确认排除项（验收对照表、外部接口章节）未出现在任何 Task 中。
- **Placeholder scan**：Task 4 截图清单为确切文件名单；各章功能点范围指向 Task 1 清单（权威来源，非占位）；LLM 不可用的降级路径已显式写明。
- **Type consistency**：模块码（CHAT/ACT/RPT/HITL/SKILL/TPL/HIST/SYS）、文件命名规则、`build.sh` 用法在 Global Constraints 定义一次，各 Task 引用一致。
