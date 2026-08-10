#!/bin/bash
# ============================================================
# install_paraformer.sh — Paraformer-zh backend 单一安装脚本（v3.2）
# 用法: bash scripts/install_paraformer.sh
# 依赖安装到 Skill 目录下的 .venv
#        + ModelScope 模型自动下载（首次转写时触发）
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${SKILL_DIR}/.venv"
if [ ! -x "${VENV_DIR}/bin/python" ]; then
    python3 -m venv "${VENV_DIR}"
fi
PYTHON_BIN="${CNE_PYTHON_BIN:-${VENV_DIR}/bin/python}"

echo -e "${BLUE}[1/2] 安装 Paraformer-zh Python 依赖…${NC}"
"${PYTHON_BIN}" -m pip install --quiet --upgrade funasr torch torchaudio modelscope 2>&1 | tail -3
echo -e "${GREEN}  ✅ funasr / torch / torchaudio 已装${NC}"

echo -e "${BLUE}[2/2] 预下载 Paraformer-zh 模型（~953MB，国内直连）…${NC}"
"${PYTHON_BIN}" - <<'PYEOF'
import sys
sys.path.insert(0, "scripts")  # 让 import config 可用
from modelscope import snapshot_download
import os
os.environ.setdefault("MODELSCOPE_QUIET", "1")

repo = "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
print(f"  下载: {repo}")
path = snapshot_download(repo)
print(f"  ✅ Paraformer-zh 模型已就绪: {path}")
PYEOF

echo -e "${GREEN}  ✅ install_paraformer.sh 完成${NC}"
exit 0
