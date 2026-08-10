#!/bin/bash
# ============================================================
# install_sensevoice.sh — SenseVoice-Small backend 单一安装脚本（v3.2）
# 用法: bash scripts/install_sensevoice.sh
# 适合跨境案件（中粤英日韩 + 情感事件标签）
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

echo "  安装 funasr + modelscope…"
"${PYTHON_BIN}" -m pip install --quiet --upgrade funasr modelscope 2>&1 | tail -3
echo -e "${GREEN}  ✅ 依赖已装${NC}"

echo "  预下载 SenseVoiceSmall 模型（~896MB，2-5 分钟）…"
"${PYTHON_BIN}" - <<'PYEOF'
import os
os.environ.setdefault("MODELSCOPE_QUIET", "1")
from modelscope import snapshot_download

repo = "iic/SenseVoiceSmall"
print(f"  下载: {repo}")
path = snapshot_download(repo)
print(f"  ✅ SenseVoiceSmall 已就绪: {path}")
PYEOF

echo -e "${GREEN}  ✅ install_sensevoice.sh 完成${NC}"
exit 0
