# LLM 网关超时 / 延迟过高

## 常见原因
- 网关侧负载高或模型服务重启中（探测能通但 chat 慢）
- LLM_API_KEY 失效（伴随 401/403 日志）
- 主应用 LLM_TIMEOUT_SECONDS 配置小于模型实际推理耗时

## 处置步骤
1. 看日志中是否有 401/403：有 → 联系网关管理员更新 key，改 `backend/.env` 的 LLM_API_KEY
2. 网关探测通但慢 → 联系网关管理员确认负载；临时可调大 `backend/.env` 的
   LLM_TIMEOUT_SECONDS（注意必须小于 nginx proxy_read_timeout）
3. 调整配置后重启主应用生效
