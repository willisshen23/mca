# ops-assistant 内存溢出排查能力增量设计

- 日期：2026-08-06
- 状态：待确认
- 关联：[2026-08-06-ops-assistant-design.md](2026-08-06-ops-assistant-design.md)（主规格）
- 背景：主规格交付的 ops-assistant 对内存溢出仅有间接感知（日志 MemoryError 聚类 + 整机 mem_pct 采集但无规则消费）。本增量补齐内存溢出的专项排查能力。

## 范围与决策

### 1. 采集：主应用进程级内存（system 采集器扩展）

`system.collect` 的 metrics 增加两个键（既有四键不变）：

- `proc_pid`：主应用进程 pid；`proc_rss_mb`：其常驻内存（MB，保留 1 位小数）
- pid 解析顺序：`settings.main_pid_file` → 扫描 `/proc/*/cmdline` 匹配 `uvicorn` + `src.main`（覆盖 start-offline.sh 前台启动不写 pid 文件的生产形态）
- 均不可用时两个键为 `None`（开发机 macOS 无 /proc 亦为此路径），不报错

### 2. 规则：新增第 8 条 `memory-usage`

judge `memory_usage`（builtins.py），rules.yaml 参数 `{mem_warn_pct: 85, mem_red_pct: 95, rss_warn_mb: 2048, rss_red_mb: 3072}`（生产服务器内存 ≥4GB，主应用 RSS 超 3GB 视为危险）：

- `mem_pct >= 95` → 红"整机内存使用率过高"；`>= 85` → 黄
- `proc_rss_mb >= 3072` → 红"主应用进程内存过高"；`>= 2048` → 黄（与整机水位取最严重级别，一条 check 只出一个结果）
- 两者均 None → 绿（与其他采集失败的 gray 区分：采集成功但无数据视为无异常）

### 3. 趋势：巡检快照驱动（诊断证据增强）

- 新模块 `ops/src/diagnosis/trend.py`：`memory_trend(db, hours=3) -> dict`，从最近 3 小时巡检快照提取 `mem_pct` 时间序列，返回 `{"points": [{"t","mem_pct"}...], "slope_pct_per_hour": float|None}`；快照 <2 条时 slope 为 None
- 斜率算法：首尾线性差 / 实际时间跨度（不做回归，快照间隔均匀时等价且可解释）
- 注入点：`run_diagnosis` 中，当剧本 collectors 含 `"system"` 时自动附加 `evidence["memory_trend"]`；不做趋势类告警规则（避免误报，趋势交由 LLM 结合证据判断）

### 4. 诊断：新增 `memory-usage` 剧本 + 出厂 runbook

- PLAYBOOKS 增加 `"memory-usage": Playbook("memory-usage", "内存溢出诊断", ("system", "logs"), "memory-oom")`
- 新增 `ops/runbooks/seed/memory-oom.md`，内容覆盖本项目实际 OOM 诱因：
  - `LLM_MAX_TOKENS` 过大导致单请求上下文占用过高
  - WeasyPrint 生成 PDF 报告时的内存峰值
  - LangGraph checkpoints.db 长期累积与会话状态膨胀
  - 处置：看 RSS 趋势确认泄漏 vs 峰值、临时降配、联系开发侧的边界
- 既有环境升级时 `seed_runbooks` 的 INSERT OR IGNORE 语义保证新 runbook 自动补入、不覆盖用户编辑

### 5. 测试

- system 采集器：pid 文件命中 / proc 扫描命中 / 均无 → None 三例（/proc 读取全部 monkeypatch）
- judge：mem_pct 越线红/黄、proc_rss 越线红/黄、双指标取最严重、全 None 为绿
- trend：空表 / 单条快照 slope=None / 三条快照斜率正确 / 只取时间窗内快照
- pipeline：`memory-usage` 在 PLAYBOOKS 中；含 system 的剧本证据包含 memory_trend 键
- 既有断言同步更新：`len(rules) == 7 → 8`；playbooks 覆盖测试的 check_id 元组加 `memory-usage`

## 明确不做（YAGNI）

- 不做内存趋势告警规则（仅进诊断证据）
- 不做堆内分析（tracemalloc / objgraph 需侵入主应用进程，违反只读红线）
- 不采集其他进程的内存（只关注主应用）
