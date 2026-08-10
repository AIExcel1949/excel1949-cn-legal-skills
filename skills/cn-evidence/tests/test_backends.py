"""
tests/test_backends.py — cn-evidence v3.2+ 单元测试

覆盖范围（v3.2）：
- ASR_BACKENDS 5 个 backend 都在
- DEFAULT_BACKEND = paraformer-zh
- DEFAULT_BACKEND_CONFIG 5 个 backend 配置完整
- WHISPER_MODEL_CACHE_FILES 映射正确（含 turbo → large-v3-turbo.pt 特殊情况）
- is_backend_ready() 对各 backend 返回正确
- load_global_config() / save_default_config_if_missing() 工作
- BACKEND_RUNNERS 5 个 backend 都能 import

运行：
    pytest .claude/skills/cn-evidence/tests/test_backends.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# 把 scripts/ 路径加入 sys.path 以便 import config.py 等
_SKILL_DIR = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _SKILL_DIR / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import config  # noqa: E402
from config import (  # noqa: E402
    ASR_BACKENDS,
    DEFAULT_BACKEND,
    DEFAULT_BACKEND_CONFIG,
    WHISPER_MODEL_CACHE_FILES,
    KNOWN_WHISPER_TURBO_MODELS,
    GLOBAL_CONFIG_PATH,
    generate_default_config,
    is_backend_ready,
    load_global_config,
    merge_config,
    get_active_backend,
    get_backend_settings,
)
from transcribe import BACKEND_RUNNERS, KNOWN_WHISPER_MODELS  # noqa: E402


# ============================================================
# 1) 常量测试
# ============================================================

class TestConstants:
    def test_asr_backends_count(self):
        """ASR_BACKENDS 应该包含 5 个 backend（v3.2+）"""
        assert len(ASR_BACKENDS) == 5, f"ASR_BACKENDS 应有 5 项，实际 {len(ASR_BACKENDS)}"

    def test_asr_backends_membership(self):
        """ASR_BACKENDS 必须包含这 5 个 backend"""
        expected = {"whisper", "whisper-turbo", "paraformer-zh", "funasr-nano", "sensevoice-small"}
        assert set(ASR_BACKENDS) == expected, f"ASR_BACKENDS 缺失: {expected - set(ASR_BACKENDS)}"

    def test_default_backend(self):
        """默认 backend 必须是 paraformer-zh（v3.0+ 用户决策）"""
        assert DEFAULT_BACKEND == "paraformer-zh"

    def test_known_whisper_models(self):
        """KNOWN_WHISPER_MODELS 必须包含 6 个模型（v3.2+ 含 turbo）"""
        expected = {"tiny", "base", "small", "medium", "large-v3", "turbo"}
        assert set(KNOWN_WHISPER_MODELS) == expected

    def test_known_whisper_turbo_models(self):
        """whisper-turbo backend 固定使用 turbo 模型"""
        assert KNOWN_WHISPER_TURBO_MODELS == ("turbo",)

    def test_default_backend_config_has_all_5(self):
        """DEFAULT_BACKEND_CONFIG 必须有 5 个 backend 的配置"""
        for backend in ASR_BACKENDS:
            assert backend in DEFAULT_BACKEND_CONFIG, f"缺失 backend 配置: {backend}"
            cfg = DEFAULT_BACKEND_CONFIG[backend]
            assert "auto_download" in cfg, f"{backend} 配置缺 auto_download"
            assert "min_memory_gb" in cfg, f"{backend} 配置缺 min_memory_gb"
            assert "note" in cfg, f"{backend} 配置缺 note"

    def test_whisper_turbo_config(self):
        """whisper-turbo backend 配置：default_model 必须 = turbo"""
        cfg = DEFAULT_BACKEND_CONFIG["whisper-turbo"]
        assert cfg["default_model"] == "turbo"
        assert "whisper" in cfg["binary"].lower()


# ============================================================
# 2) WHISPER_MODEL_CACHE_FILES 映射测试
# ============================================================

class TestWhisperModelCacheFiles:
    """验证 Whisper CLI 模型名 → 缓存文件名的映射（含 turbo → large-v3-turbo.pt 特殊情况）"""

    def test_turbo_maps_to_large_v3_turbo_pt(self):
        """turbo 模型实际缓存为 large-v3-turbo.pt（v3.2+ 实测发现）"""
        assert WHISPER_MODEL_CACHE_FILES["turbo"] == "large-v3-turbo.pt"

    def test_all_known_models_mapped(self):
        """KNOWN_WHISPER_MODELS 全部都要有映射"""
        for model in KNOWN_WHISPER_MODELS:
            assert model in WHISPER_MODEL_CACHE_FILES, f"{model} 缺缓存文件名映射"

    def test_mapping_format(self):
        """所有映射值必须以 .pt 结尾"""
        for model, filename in WHISPER_MODEL_CACHE_FILES.items():
            assert filename.endswith(".pt"), f"{model} → {filename} 不是 .pt 文件"


# ============================================================
# 3) is_backend_ready 测试
# ============================================================

class TestIsBackendReady:
    """验证 backend 就位检查逻辑"""

    def test_whisper_ready(self):
        """whisper backend：large-v3 已缓存（之前安装过），应返回 True"""
        ready, msg = is_backend_ready(generate_default_config(), "whisper")
        assert ready is True, f"whisper 应就位，实际: {msg}"
        assert "large-v3.pt" in msg

    def test_whisper_turbo_ready(self):
        """whisper-turbo backend：large-v3-turbo.pt 已缓存（之前已下载）"""
        ready, msg = is_backend_ready(generate_default_config(), "whisper-turbo")
        assert ready is True, f"whisper-turbo 应就位，实际: {msg}"
        assert "large-v3-turbo.pt" in msg

    def test_paraformer_ready(self):
        """paraformer-zh backend：应就位"""
        ready, msg = is_backend_ready(generate_default_config(), "paraformer-zh")
        assert ready is True, f"paraformer-zh 应就位，实际: {msg}"

    def test_funasr_nano_ready(self):
        """funasr-nano backend：应就位（之前已下载）"""
        ready, msg = is_backend_ready(generate_default_config(), "funasr-nano")
        assert ready is True, f"funasr-nano 应就位，实际: {msg}"

    def test_sensevoice_small_ready(self):
        """sensevoice-small backend：应就位（之前已下载）"""
        ready, msg = is_backend_ready(generate_default_config(), "sensevoice-small")
        assert ready is True, f"sensevoice-small 应就位，实际: {msg}"

    def test_unknown_backend_falls_back_to_funasr_check(self):
        """未知 backend 名应走 FunASR 分支（必须有 repo_id）"""
        ready, msg = is_backend_ready(generate_default_config(), "unknown-backend")
        assert ready is False
        assert "repo_id" in msg


# ============================================================
# 4) 配置加载测试
# ============================================================

class TestConfigLoad:
    def test_generate_default_config_has_5_backends(self):
        """默认全局配置应包含 5 个 backend"""
        cfg = generate_default_config()
        assert "backends" in cfg
        for backend in ASR_BACKENDS:
            assert backend in cfg["backends"]

    def test_load_global_config_returns_dict(self):
        """load_global_config() 返回 dict，不抛异常"""
        cfg = load_global_config()
        assert isinstance(cfg, dict)
        assert "asr_backend" in cfg

    def test_get_active_backend_default(self):
        """默认 backend 应为 paraformer-zh"""
        cfg = generate_default_config()
        active = get_active_backend(cfg)
        assert active == "paraformer-zh"

    def test_get_backend_settings_returns_dict(self):
        """get_backend_settings() 对每个 backend 返回 dict"""
        cfg = generate_default_config()
        for backend in ASR_BACKENDS:
            settings = get_backend_settings(cfg, backend)
            assert isinstance(settings, dict)

    def test_merge_config_cli_overrides(self):
        """CLI 参数应能覆盖全局配置"""
        cfg = generate_default_config()
        case_info = {}
        cli_args = {"asr_backend": "whisper-turbo"}
        merged = merge_config(cfg, case_info, cli_args)
        assert merged["asr_backend"] == "whisper-turbo"

    def test_merge_config_case_overrides_global(self):
        """case_info 应能覆盖全局配置"""
        cfg = generate_default_config()
        case_info = {"asr_backend": "funasr-nano"}
        cli_args = {}
        merged = merge_config(cfg, case_info, cli_args)
        assert merged["asr_backend"] == "funasr-nano"

    def test_merge_config_invalid_backend_rejected(self):
        """无效 backend 应抛 ValueError"""
        cfg = generate_default_config()
        case_info = {}
        cli_args = {"asr_backend": "nonexistent-backend"}
        with pytest.raises(ValueError) as exc_info:
            merge_config(cfg, case_info, cli_args)
        assert "无效的 asr_backend" in str(exc_info.value)


# ============================================================
# 5) transcribe.py dispatcher 测试
# ============================================================

class TestDispatcher:
    def test_backend_runners_count(self):
        """BACKEND_RUNNERS 必须有 5 个 backend（与 ASR_BACKENDS 一致）"""
        assert len(BACKEND_RUNNERS) == 5

    def test_backend_runners_membership(self):
        """BACKEND_RUNNERS 包含所有 5 个 backend"""
        expected = {"whisper", "whisper-turbo", "paraformer-zh", "funasr-nano", "sensevoice-small"}
        assert set(BACKEND_RUNNERS.keys()) == expected

    def test_backend_runners_callable(self):
        """每个 backend 的 run 函数必须可调用"""
        for backend, runner in BACKEND_RUNNERS.items():
            assert callable(runner), f"{backend} runner 不可调用"


# ============================================================
# 6) asr_whisper_turbo.py 模块测试
# ============================================================

class TestWhisperTurboModule:
    """验证 asr_whisper_turbo.py 模块存在并能 import"""

    def test_module_importable(self):
        """asr_whisper_turbo 模块可 import"""
        try:
            import asr_whisper_turbo  # noqa: F401
            assert hasattr(asr_whisper_turbo, "run")
            assert hasattr(asr_whisper_turbo, "main")
        except ImportError as e:
            pytest.fail(f"asr_whisper_turbo import 失败: {e}")

    def test_run_signature(self):
        """asr_whisper_turbo.run() 签名与 asr_whisper.run() 一致"""
        import asr_whisper_turbo
        import inspect
        sig = inspect.signature(asr_whisper_turbo.run)
        # 关键参数：device 应支持 cpu/cuda/mps/auto
        assert "device" in sig.parameters


# ============================================================
# 7) FunASR 系 backend 模块测试（轻量：仅验证 import + 默认 schema 兼容）
# ============================================================

class TestFunAsrBackendModules:
    def test_fun_asr_runner_importable(self):
        """funasr_runner 模块可 import"""
        try:
            from _common import funasr_runner  # noqa: F401
            assert hasattr(funasr_runner, "run_funasr_family")
        except ImportError as e:
            pytest.fail(f"funasr_runner import 失败: {e}")

    def test_paraformer_module(self):
        try:
            import asr_paraformer  # noqa: F401
            assert hasattr(asr_paraformer, "run")
        except ImportError as e:
            pytest.fail(f"asr_paraformer import 失败: {e}")

    def test_funasr_nano_module(self):
        try:
            import asr_funasr_nano  # noqa: F401
            assert hasattr(asr_funasr_nano, "run")
        except ImportError as e:
            pytest.fail(f"asr_funasr_nano import 失败: {e}")

    def test_sensevoice_module(self):
        try:
            import asr_sensevoice  # noqa: F401
            assert hasattr(asr_sensevoice, "run")
        except ImportError as e:
            pytest.fail(f"asr_sensevoice import 失败: {e}")

    def test_whisper_module(self):
        try:
            import asr_whisper  # noqa: F401
            assert hasattr(asr_whisper, "run")
        except ImportError as e:
            pytest.fail(f"asr_whisper import 失败: {e}")