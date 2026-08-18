#!/usr/bin/env bash
# 用法：bash docs/功能说明书/build.sh
# 按章号顺序拼接 chapters/*.md → 功能说明书.md，并转 docx（自动目录）
set -euo pipefail
cd "$(dirname "$0")"
for f in chapters/*.md; do cat "$f"; echo; done > 功能说明书.md
pandoc 功能说明书.md \
  -o 功能说明书.docx \
  --reference-doc=reference.docx \
  --toc --toc-depth=3 \
  -M title="活动分析助手 功能说明书"
echo "已生成 功能说明书.md / 功能说明书.docx"
