# 活动分析助手 — Docker 打包部署指南

> **本文内容已整合进 [DEPLOY.md](DEPLOY.md)**（2026-08-23 起 DEPLOY.md 为部署总入口，
> 涵盖 tar 包、Docker、LLM API Key 密文三部分）。请直接查阅：
>
> - Docker 部署方式总览与架构：[DEPLOY.md 第 1、2 章](DEPLOY.md#1-系统架构)
> - 快速部署（可联网）：[DEPLOY.md 5.2](DEPLOY.md#52-快速部署可联网环境)
> - 离线镜像打包与导入（内网，含 **arm64 按架构出包** 与 pyc-only 编译说明）：[DEPLOY.md 5.3](DEPLOY.md#53-离线镜像打包与导入内网环境)
> - Docker 配置要点（端口 / 强制环境变量）：[DEPLOY.md 5.4](DEPLOY.md#54-docker-配置要点)
> - LLM API Key 密文（含 Docker 下主密钥注入）：[DEPLOY.md 第 7 章](DEPLOY.md#7-llm-api-key-密文)
> - 数据与备份 / 运维 / 更新：[DEPLOY.md 8-10 章](DEPLOY.md#8-运维管理)
> - 故障排查：[DEPLOY.md 第 11 章](DEPLOY.md#11-故障排查)
>
> 更细的主题另见：
>
> - [deploy/docker/DOCKER-SQLITE-DEPLOY.md](deploy/docker/DOCKER-SQLITE-DEPLOY.md) — Docker Compose + SQLite 部署细节
> - [deploy/WINDOWS11-DOCKER-OFFLINE-BUILD.md](deploy/WINDOWS11-DOCKER-OFFLINE-BUILD.md) — Windows 11 用 Docker 构建麒麟离线 tar 包
> - [DEPLOY-OFFLINE-KYLIN.md](DEPLOY-OFFLINE-KYLIN.md) — 麒麟 V10 全离线部署（便携 Python）
