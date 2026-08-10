#!/bin/bash
# ============================================================
# cn-evidence v3.2 — 依赖一键安装脚本
# 用法: bash scripts/install.sh              # 交互式
#       bash scripts/install.sh --full       # 装齐 5 backend 全部模型
#       bash scripts/install.sh --backend paraformer-zh  # 单装 1 个
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FULL_MODE=false
BACKEND_ONLY=""

while [ $# -gt 0 ]; do
    case "$1" in
        --full)        FULL_MODE=true ;;
        --backend)     shift; BACKEND_ONLY="$1" ;;
        -h|--help)
            echo "用法: bash scripts/install.sh [--full] [--backend <name>]"
            echo "  --full         装齐 5 backend 全部模型"
            echo "  --backend NAME 单装某 backend (paraformer-zh | funasr-nano | sensevoice-small | whisper | whisper-turbo)"
            exit 0
            ;;
    esac
    shift
done

# 模式：单装 1 个 backend
if [ -n "$BACKEND_ONLY" ]; then
    case "$BACKEND_ONLY" in
        paraformer-zh)   script="install_paraformer.sh" ;;
        funasr-nano)     script="install_funasr_nano.sh" ;;
        sensevoice-small) script="install_sensevoice.sh" ;;
        whisper)         script="install_whisper.sh" ;;
        whisper-turbo)   script="install_whisper.sh"; export WHISPER_MODEL=turbo ;;
        *)
            echo "未知 backend: $BACKEND_ONLY" >&2; exit 1 ;;
    esac
    bash "${SKILL_DIR}/scripts/${script}"
    echo -e "${GREEN}✅ ${BACKEND_ONLY} backend 安装完成${NC}"
    exit 0
fi

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}  cn-evidence v3.2 — 依赖安装${NC}"
echo -e "${BLUE}  Skill 目录: ${SKILL_DIR}${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""

# ---- 检查 Homebrew ----
echo -e "${YELLOW}[1/7] 检查 Homebrew...${NC}"
if command -v brew &> /dev/null; then
    echo -e "${GREEN}  ✅ Homebrew 已安装${NC}"
else
    echo -e "${RED}  ❌ Homebrew 未安装。请先安装: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"${NC}"
    exit 1
fi

# ---- 基础依赖 ----
echo ""
echo -e "${YELLOW}[2/7] 安装基础依赖 (ffmpeg)...${NC}"

if command -v ffmpeg &> /dev/null; then
    echo -e "${GREEN}  ✅ ffmpeg 已安装${NC}"
else
    echo "  安装 ffmpeg..."
    brew install ffmpeg
fi

# ---- Python 基础依赖 ----
echo ""
echo -e "${YELLOW}[3/7] 创建 .venv 并安装 Python 基础依赖...${NC}"
VENV_DIR="${SKILL_DIR}/.venv"
if [ ! -x "${VENV_DIR}/bin/python" ]; then
    python3 -m venv "${VENV_DIR}"
fi
PYTHON_BIN="${VENV_DIR}/bin/python"
export CNE_PYTHON_BIN="${PYTHON_BIN}"
"${PYTHON_BIN}" -m pip install --quiet --upgrade pip
"${PYTHON_BIN}" -m pip install --quiet pyyaml python-docx modelscope 2>&1 | tail -1
echo -e "${GREEN}  ✅ PyYAML, python-docx, modelscope 已安装${NC}"

# ---- Stage 4：5 个 ASR backend ----
echo ""
echo -e "${YELLOW}[4/7] 安装 ASR backend（5 选 N）...${NC}"
echo ""
echo -e "${BLUE}  💡 选型建议：先用本案 3—5 分钟代表性片段评测速度与错误率。${NC}"
echo -e "${BLUE}     - 资源受限的设备：可先测试 Whisper small 或 turbo${NC}"
echo -e "${BLUE}     - 中文普通话：默认 paraformer-zh${NC}"
echo -e "${BLUE}     - 粤语或跨语种：可测试 sensevoice-small${NC}"
echo -e "${BLUE}     - 敏感案件：默认本地处理，不自动上传云端${NC}"
echo ""
BACKENDS=(paraformer-zh funasr-nano sensevoice-small whisper whisper-turbo)
BACKEND_SCRIPTS=(install_paraformer.sh install_funasr_nano.sh install_sensevoice.sh install_whisper.sh install_whisper.sh)
BACKEND_DEFAULT_Y=("y" "n" "n" "n" "n")  # 默认仅装 paraformer-zh

for i in "${!BACKENDS[@]}"; do
    backend="${BACKENDS[$i]}"
    install_script_name="${BACKEND_SCRIPTS[$i]}"
    default_yn="${BACKEND_DEFAULT_Y[$i]}"
    if [ "$FULL_MODE" = true ]; then
        yn="y"
    else
        if [ "$backend" = "whisper" ]; then
            # Whisper backend：询问默认模型
            echo -e "${BLUE}  Whisper 模型选择（默认 medium）：${NC}"
            echo "    1) tiny      (体积小，仅建议测试)"
            echo "    2) base      (体积较小)"
            echo "    3) small     (Mac CPU 可先测试)"
            echo "    4) medium    (资源占用较高)"
            echo "    5) large-v3  (资源占用高，须样本评测)"
            echo "    6) turbo     (速度与资源平衡档)"
            read -p "  Whisper 模型 [3]: " whisper_model_choice
            whisper_model_choice=${whisper_model_choice:-3}
            case "$whisper_model_choice" in
                1) WHISPER_MODEL="tiny" ;;
                2) WHISPER_MODEL="base" ;;
                4) WHISPER_MODEL="medium" ;;
                5) WHISPER_MODEL="large-v3" ;;
                6) WHISPER_MODEL="turbo" ;;
                *) WHISPER_MODEL="small" ;;
            esac
            echo -e "${BLUE}  ▶ 选择 Whisper 模型: $WHISPER_MODEL${NC}"
            export WHISPER_MODEL
        fi
        read -p "  是否安装 $backend (${default_yn^^})? [y/N]: " yn
        yn=${yn:-$default_yn}
    fi
    yn_lc=$(echo "$yn" | tr '[:upper:]' '[:lower:]')
    echo ""
    if [ "$yn_lc" = "y" ]; then
        install_script="${SKILL_DIR}/scripts/${install_script_name}"
        if [ -f "$install_script" ]; then
            echo -e "${BLUE}  ▶ 安装 $backend...${NC}"
            if [ "$backend" = "whisper-turbo" ]; then
                WHISPER_MODEL=turbo bash "$install_script"
            else
                bash "$install_script"
            fi
            echo -e "${GREEN}  ✅ $backend 安装完成${NC}"
        else
            echo -e "${YELLOW}  ⚠️  $install_script_name 不存在，跳过${NC}"
        fi
    else
        echo "  跳过 $backend"
    fi
    echo ""
done

# ---- Stage 5：sherpa-onnx（备选说话人分离）----
echo -e "${YELLOW}[5/7] sherpa-onnx（备选说话人分离，仅分离不含 ASR）...${NC}"
echo -e "  ${BLUE}43MB 模型超轻量，可作为 transcribe.py --diarize-method sherpa-onnx 的后端${NC}"
if [ "$FULL_MODE" = true ]; then
    yn="y"
else
    read -p "  是否安装 sherpa-onnx? [y/N]: " yn
    yn=${yn:-n}
fi
if [ "$(echo "$yn" | tr '[:upper:]' '[:lower:]')" = "y" ]; then
    "${PYTHON_BIN}" -m pip install --quiet sherpa-onnx 2>&1 | tail -1
    MODEL_DIR="$HOME/.cache/sherpa-onnx"
    mkdir -p "$MODEL_DIR"
    if [ ! -f "$MODEL_DIR/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx" ]; then
        echo "  下载 embedding 模型 (40MB)..."
        curl -SL --progress-bar -o "$MODEL_DIR/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx" \
            "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
    fi
    if [ ! -d "$MODEL_DIR/sherpa-onnx-pyannote-segmentation-3-0" ]; then
        echo "  下载 segmentation 模型 (7MB)..."
        curl -SL --progress-bar -o "/tmp/sherpa-seg.tar.bz2" \
            "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
        tar xf "/tmp/sherpa-seg.tar.bz2" -C "$MODEL_DIR"
        rm "/tmp/sherpa-seg.tar.bz2"
    fi
    echo -e "${GREEN}  ✅ sherpa-onnx 已安装${NC}"
else
    echo "  跳过 sherpa-onnx"
fi
echo ""

# ---- Stage 6：whisperX（跨境备份，需 HF_ENDPOINT）----
echo -e "${YELLOW}[6/7] whisperX（跨境备份）...${NC}"
echo -e "  ${BLUE}需设置 HF_ENDPOINT=https://hf-mirror.com${NC}"
if [ "$FULL_MODE" = true ]; then
    yn="y"
else
    read -p "  是否安装 whisperX? [y/N]: " yn
    yn=${yn:-n}
fi
if [ "$(echo "$yn" | tr '[:upper:]' '[:lower:]')" = "y" ]; then
    export HF_ENDPOINT=https://hf-mirror.com
    "${PYTHON_BIN}" -m pip install --quiet whisperx 2>&1 | tail -1
    echo -e "${GREEN}  ✅ whisperX 已装${NC}"
    echo -e "${YELLOW}  💡 建议: export HF_ENDPOINT=https://hf-mirror.com 写入 ~/.zshrc${NC}"
else
    echo "  跳过 whisperX"
fi
echo ""

# ---- Stage 7：腾讯云 SDK（云端备选）----
echo -e "${YELLOW}[7/7] 腾讯云 SDK（云端 ASR）...${NC}"
echo -e "  ${YELLOW}仅在已完成当事人授权、委托处理和数据安全审查时安装并使用。${NC}"
if [ "$FULL_MODE" = true ]; then
    yn="y"
else
    read -p "  是否安装腾讯云 SDK? [y/N]: " yn
    yn=${yn:-n}
fi
if [ "$(echo "$yn" | tr '[:upper:]' '[:lower:]')" = "y" ]; then
    "${PYTHON_BIN}" -m pip install --quiet tencentcloud-sdk-python 2>&1 | tail -1
    echo -e "${GREEN}  ✅ 腾讯云 SDK 已装${NC}"
    echo -e "${YELLOW}  💡 设置 TENCENT_SECRET_ID 与 TENCENT_SECRET_KEY 环境变量${NC}"
else
    echo "  跳过腾讯云 SDK"
fi
echo ""

# ---- 完成 ----
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  ✅ 安装完成！${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "  验证安装:"
echo "    cd ${SKILL_DIR}"
echo "    source .venv/bin/activate"
echo "    python scripts/config.py doctor    # 5 backend 就位状态"
echo "    python scripts/transcribe.py --help"
echo "    python scripts/asr_paraformer.py --help"
echo ""
echo "  快速开始（默认 paraformer-zh）:"
echo "    python scripts/transcribe.py --input 录音.mp3 --num-speakers 2"
echo ""
echo "  或直跑特定 backend:"
echo "    python3 scripts/asr_paraformer.py --input 录音.mp3 --num-speakers 2"
echo "    python3 scripts/asr_whisper.py --input 录音.mp3 --whisper-model large-v3"
echo "    python3 scripts/asr_sensevoice.py --input 录音.mp3 --num-speakers 2"
echo ""
