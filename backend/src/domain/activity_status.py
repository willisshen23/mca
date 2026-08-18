"""活动状态码 → 展示文案（与前端 utils/activityDictionaries.js 对齐）。"""
from __future__ import annotations

import re

ACTIVITY_STATUS_LABELS = {
    "A1": "已删除",
    "A2": "未提交",
    "A3": "已上线",
    "A6": "已下线",
    "A7": "审批中",
    "A8": "审批通过",
    "A9": "审批驳回",
    "B01": "策划",
    "B02": "待审批",
    "B03": "待执行",
    "B04": "执行中",
    "B05": "暂停",
    "B06": "已结束",
    "B07": "提前下线",
    "C0": "未查看",
    "C3": "发布中",
    "C4": "终止",
    "C5": "过期关闭",
    "C6": "提前终止",
    "D1": "上线",
    "D0": "下线",
    "Y0": "草稿",
    "Y1": "已发布",
    "Y2": "一级审批通过",
    "Y3": "审批通过",
    "Y4": "审批不通过",
    "Y5": "审批超时",
    "Y6": "进行中",
    "Y7": "提前终止",
    "Y8": "活动结束",
}

_SCOPE_SUFFIX = re.compile(r"\s*[（(][^）)]*[）)]\s*$")


def display_activity_status(status: object) -> str:
    """状态码转中文文案；未知码返回原文（去掉末尾括号范围注释）。"""
    raw = str(status or "").strip()
    label = ACTIVITY_STATUS_LABELS.get(raw.upper())
    if label:
        return label
    return _SCOPE_SUFFIX.sub("", raw).strip()
