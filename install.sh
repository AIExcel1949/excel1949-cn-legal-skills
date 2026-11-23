#!/usr/bin/env bash
# ==============================================================================
# excel1949 中国法律专家团 (excel1949-cn-legal-skills) 安装与同步脚本 (macOS / Linux)
# 适配主流智能体生态:
#   - Google Antigravity / Gemini (~/.gemini/config/plugins/excel1949-cn-legal-skills)
#   - Anthropic Claude Code       (~/.claude/plugins/cache/excel1949-cn-legal-marketplace/excel1949-cn-legal-skills/<ver>)
#   - OpenAI Codex CLI            (~/.codex/plugins/cache/excel1949-marketplace/excel1949-cn-legal-skills/<ver>)
#   - Universal Agent Skills      (~/.agents/skills/cn-*)
#
# 默认行为: 物理拷贝（独立实体目录，彻底脱离对本仓库路径的依赖）
# 开发者模式: 传入 --link 可使用软链接 (仅供本地开发调试)
# WorkBuddy 专版请切换至 workbuddy 分支或使用专版 zip 包导入。
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_NAME="excel1949-cn-legal-skills"
USE_SYMLINK=false

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    echo "用法: ./install.sh [--link]"
    echo "  默认: 实体拷贝安装到 Antigravity / Claude Code / Codex CLI / ~/.agents/skills"
    echo "  --link: 软链接模式（仅限本地开发调试）"
    exit 0
fi

if [ "${1:-}" = "--link" ]; then
    USE_SYMLINK=true
    echo "[MODE] 软链接模式 (--link)"
else
    echo "[MODE] 实体拷贝安装模式 (默认，各智能体目录自包含独立运行)"
fi

get_plugin_version() {
    local pjson="$SCRIPT_DIR/plugin.json"
    if [ -f "$pjson" ]; then
        python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("version", "1.0.1"))' "$pjson" 2>/dev/null || echo "1.0.1"
    else
        echo "1.0.1"
    fi
}

PLUGIN_VER="$(get_plugin_version)"
echo "=== 开始安装/同步 $PLUGIN_NAME (v$PLUGIN_VER) ==="
echo "源码根目录: $SCRIPT_DIR"

deploy_plugin_tree() {
    local dest="$1"
    rm -rf "$dest"
    mkdir -p "$(dirname "$dest")"
    if [ "$USE_SYMLINK" = true ]; then
        ln -sfn "$SCRIPT_DIR" "$dest"
    else
        mkdir -p "$dest"
        tar -C "$SCRIPT_DIR" \
            --exclude='.git' \
            --exclude='.DS_Store' \
            --exclude='__pycache__' \
            --exclude='*.pyc' \
            --exclude='.venv' \
            --exclude='.in_use' \
            -cf - . | tar -C "$dest" -xf -
    fi
}

deploy_dir() {
    local src="$1"
    local dest="$2"
    rm -rf "$dest"
    mkdir -p "$(dirname "$dest")"
    if [ "$USE_SYMLINK" = true ]; then
        ln -sfn "$src" "$dest"
    else
        cp -R "$src" "$dest"
    fi
}

# 1. Google Antigravity / Gemini (~/.gemini/config/plugins)
GEMINI_PLUGIN_DIR="$HOME/.gemini/config/plugins"
if [ -d "$GEMINI_PLUGIN_DIR" ] || [ -d "$HOME/.gemini" ]; then
    echo "-> 正在安装至 Google Antigravity / Gemini ($GEMINI_PLUGIN_DIR/$PLUGIN_NAME)..."
    deploy_plugin_tree "$GEMINI_PLUGIN_DIR/$PLUGIN_NAME"
    echo "   [OK] 已安装 Antigravity / Gemini: $PLUGIN_NAME (v$PLUGIN_VER)"
fi

# 2. Anthropic Claude Code (~/.claude/plugins/cache/excel1949-cn-legal-marketplace)
CLAUDE_CACHE_BASE="$HOME/.claude/plugins/cache/excel1949-cn-legal-marketplace"
if command -v claude >/dev/null 2>&1 || [ -d "$HOME/.claude" ]; then
    echo "-> 正在同步 Anthropic Claude Code ($CLAUDE_CACHE_BASE/$PLUGIN_NAME/$PLUGIN_VER)..."
    rm -rf "$CLAUDE_CACHE_BASE/$PLUGIN_NAME"
    deploy_plugin_tree "$CLAUDE_CACHE_BASE/$PLUGIN_NAME/$PLUGIN_VER"
    echo "   [OK] 已同步 Claude Code 插件: $PLUGIN_NAME (v$PLUGIN_VER)"
fi

# 3. OpenAI Codex CLI (~/.codex/plugins/cache/excel1949-marketplace)
CODEX_BASE="$HOME/.codex/plugins/cache/excel1949-marketplace"
if [ -d "$HOME/.codex" ]; then
    echo "-> 正在安装至 OpenAI Codex CLI ($CODEX_BASE/$PLUGIN_NAME/$PLUGIN_VER)..."
    rm -rf "$CODEX_BASE/$PLUGIN_NAME"
    deploy_plugin_tree "$CODEX_BASE/$PLUGIN_NAME/$PLUGIN_VER"
    echo "   [OK] 已安装 OpenAI Codex CLI: $PLUGIN_NAME (v$PLUGIN_VER)"
fi

# 4. Universal Agent Skills (~/.agents/skills)
AGENTS_SKILL_BASE="$HOME/.agents/skills"
echo "-> 正在同步 40 项法律技能至 Universal Agent Skills ($AGENTS_SKILL_BASE)..."
mkdir -p "$AGENTS_SKILL_BASE"
for s in "$SCRIPT_DIR/skills"/*; do
    if [ -d "$s" ] && [ -f "$s/SKILL.md" ]; then
        s_name="$(basename "$s")"
        deploy_dir "$s" "$AGENTS_SKILL_BASE/$s_name"
    fi
done
echo "   [OK] 已同步全量法律技能至 $AGENTS_SKILL_BASE"

echo ""
echo "================================================================================"
echo "$PLUGIN_NAME (v$PLUGIN_VER) 安装完成！"
echo "  已同步目标: Google Antigravity (Gemini) / Claude Code / OpenAI Codex / ~/.agents/skills"
echo "  包含内容: 40 项中国法律 Skill + 8 个专家角色 + 17 个藏经阁领域知识包"
echo "================================================================================"
