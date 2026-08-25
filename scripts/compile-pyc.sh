#!/usr/bin/env bash
#
# compile-pyc.sh — 业务代码字节码编译（pyc-only 出包前置步骤）
#
# 对给定目录执行：
#   1. python -m compileall -b（旧式布局，.pyc 与 .py 同级，可无源码导入）
#   2. 删除目录内全部 .py 源码与 __pycache__ 缓存目录
#   3. 校验无 .py 残留
#
# 注意：
#   - .pyc 与 CPU 架构无关，但严格绑定 Python minor 版本（如 3.12）；
#     本脚本强制校验解释器版本与 EXPECT_PYTHON_VERSION 一致。
#   - 本操作为原地删除源码，调用方必须先复制到 staging 目录再执行，
#     切勿直接对开发工作区运行。
#   - 运维脚本（backend/scripts/*.py、offline-v3/smoke.py）不在编译范围内，
#     由调用方保留源码。
#
# 用法：
#   bash scripts/compile-pyc.sh <目录> [目录...]
#
# 环境变量：
#   COMPILE_PYTHON         编译用解释器（默认 python3.12）
#   EXPECT_PYTHON_VERSION  目标运行时 Python 版本（默认 312，即 3.12）
#
set -euo pipefail

COMPILE_PYTHON="${COMPILE_PYTHON:-python3.12}"
EXPECT_PYTHON_VERSION="${EXPECT_PYTHON_VERSION:-312}"

die() {
    printf '错误: %s\n' "$*" >&2
    exit 1
}

[ $# -ge 1 ] || die "用法: bash scripts/compile-pyc.sh <目录> [目录...]"

command -v "$COMPILE_PYTHON" >/dev/null 2>&1 || die "未找到编译解释器: $COMPILE_PYTHON"

ACTUAL_VERSION="$("$COMPILE_PYTHON" -c 'import sys; print(f"{sys.version_info.major}{sys.version_info.minor}")')"
if [ "$ACTUAL_VERSION" != "$EXPECT_PYTHON_VERSION" ]; then
    die "编译解释器版本 ($ACTUAL_VERSION) 与目标运行时 ($EXPECT_PYTHON_VERSION) 不一致，pyc 无法跨 minor 版本加载。请用 COMPILE_PYTHON 指定 Python ${EXPECT_PYTHON_VERSION}，或用 EXPECT_PYTHON_VERSION 显式声明目标版本"
fi

for dir in "$@"; do
    [ -d "$dir" ] || die "目录不存在: $dir"
    echo ">>> 编译字节码: $dir (Python $ACTUAL_VERSION)"

    # 清理开发期遗留的旧式缓存，避免与 -b 产物重复
    find "$dir" -type d -name __pycache__ -prune -exec rm -rf {} +

    # 语法错误会使 compileall 非零退出，set -e 直接中断
    "$COMPILE_PYTHON" -m compileall -q -b "$dir"

    # 删除源码，保留同级 .pyc（无源码布局，import 机制可直接加载）
    find "$dir" -type f -name '*.py' -delete
    find "$dir" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

    leftover="$(find "$dir" -type f -name '*.py' | head -1 || true)"
    [ -z "$leftover" ] || die "源码剥离不完整，仍存在: $leftover"

    pyc_count="$(find "$dir" -type f -name '*.pyc' | wc -l | tr -d ' ')"
    [ "$pyc_count" -gt 0 ] || die "编译产物为空: $dir"
    echo "    完成: $pyc_count 个 .pyc，源码已剥离"
done
