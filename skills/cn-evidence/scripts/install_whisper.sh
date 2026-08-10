#!/bin/bash
# ============================================================
# install_whisper.sh — Whisper backend 单一安装脚本（v3.2）
# 用法: bash scripts/install_whisper.sh
# 注：v3.0+ 默认 backend 是 paraformer-zh；Whisper 仍保留供向后兼容
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${SKILL_DIR}/.venv"
if [ ! -x "${VENV_DIR}/bin/python" ]; then
    python3 -m venv "${VENV_DIR}"
fi
PYTHON_BIN="${CNE_PYTHON_BIN:-${VENV_DIR}/bin/python}"

echo "  [1/2] 在 .venv 安装 openai-whisper…"
"${PYTHON_BIN}" -m pip install --quiet --upgrade openai-whisper

WHISPER_MODEL="${WHISPER_MODEL:-large-v3}"
export WHISPER_MODEL
echo "  [2/2] 预下载 Whisper ${WHISPER_MODEL} 模型…"
"${PYTHON_BIN}" - <<'PYEOF'
import os
import whisper

model_name = os.environ.get("WHISPER_MODEL", "large-v3")
whisper.load_model(model_name)
print(f"  ✅ Whisper {model_name} 已就绪")
PYEOF

echo -e "${GREEN}  ✅ install_whisper.sh 完成${NC}"
exit 0
