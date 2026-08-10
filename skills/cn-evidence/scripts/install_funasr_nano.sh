#!/bin/bash
# ============================================================
# install_funasr_nano.sh — Fun-ASR-Nano backend 单一安装脚本（v3.2）
# 用法: bash scripts/install_funasr_nano.sh
# 警告：Fun-ASR-Nano-2512 为 800M 模型，安装前应预留较多内存和磁盘空间
#        Mac M-series CPU 推理较慢；NVIDIA/Apple Silicon GPU 推荐
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}⚠️  Fun-ASR-Nano 资源占用较高；安装后请先用短样本测试${NC}"

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${SKILL_DIR}/.venv"
if [ ! -x "${VENV_DIR}/bin/python" ]; then
    python3 -m venv "${VENV_DIR}"
fi
PYTHON_BIN="${CNE_PYTHON_BIN:-${VENV_DIR}/bin/python}"

echo "  安装新版 FunASR + modelscope…"
"${PYTHON_BIN}" -m pip install --quiet --upgrade \
    git+https://github.com/modelscope/FunASR.git modelscope tiktoken huggingface_hub 2>&1 | tail -3
echo -e "${GREEN}  ✅ 依赖已装${NC}"

echo "  预下载 Fun-ASR-Nano-2512 模型…"
"${PYTHON_BIN}" - <<'PYEOF'
import os
os.environ.setdefault("MODELSCOPE_QUIET", "1")
from modelscope import snapshot_download

repo = "FunAudioLLM/Fun-ASR-Nano-2512"
print(f"  下载: {repo}")
path = snapshot_download(repo)
print(f"  ✅ Fun-ASR-Nano 已就绪: {path}")
PYEOF

echo -e "${GREEN}  ✅ install_funasr_nano.sh 完成${NC}"
exit 0
