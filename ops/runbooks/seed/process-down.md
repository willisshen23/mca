# 主应用进程宕机

## 常见原因
- 进程崩溃（看日志末尾的 Traceback）
- 服务器重启后未启动服务
- 内存不足被系统 OOM Kill

## 处置步骤
1. 查看日志目录 `backend/data/logs/` 当天的 `app-*.log`，找最后的 ERROR/Traceback
2. 如是 OOM，联系系统管理员确认内存并考虑降低 LLM_MAX_TOKENS
3. 重启服务：`cd backend && bash scripts/server.sh start`
4. 重启后确认 `curl http://127.0.0.1:8000/health` 返回 ok
