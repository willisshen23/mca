# LLM API Key 密文配置使用文档

> **本文内容已整合进 [../DEPLOY.md 第 7 章](../DEPLOY.md#7-llm-api-key-密文)**（2026-08-23 起
> DEPLOY.md 为部署总入口）。请直接查阅：
>
> - 背景与方案（算法 / 密文格式 / 主密钥来源 / 覆盖字段）：[7.1](../DEPLOY.md#71-背景与方案)
> - 快速开始（init / encrypt / check / 启动 / 审计解密）：[7.2](../DEPLOY.md#72-快速开始)
> - 各部署方式下的主密钥注入（Docker Compose / systemd / ops）：[7.3](../DEPLOY.md#73-各部署方式下的主密钥注入)
> - 密钥轮换：[7.4](../DEPLOY.md#74-密钥轮换)
> - 密文故障排查：[7.5](../DEPLOY.md#75-密文故障排查)
> - 安全边界与注意事项：[7.6](../DEPLOY.md#76-安全边界与注意事项)
> - 扩展到其他敏感字段与相关测试：[7.7](../DEPLOY.md#77-扩展到其他敏感字段)
>
> 适用范围：backend 主应用（`backend/.env`）与 ops 运维助手（`ops/.env` / 复用 `backend/.env`）。
> 配套代码：`backend/src/secrets.py`、`ops/src/secrets.py`、`backend/scripts/env_secret.py`。
