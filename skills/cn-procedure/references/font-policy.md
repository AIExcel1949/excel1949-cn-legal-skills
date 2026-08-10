# 中文字体使用说明

本 Skill 的程序文书模板使用**免费可商用**字体，确保任何环境下都能正常显示。

## 字体策略

| 角色 | 字体名 | Fallback 顺序 |
|------|--------|---------------|
| **正文** | `HarmonyOS Sans`（鸿蒙字体） | 仿宋 FangSong → 思源黑体 → 微软雅黑 → 苹方 → 黑体 |
| **标题** | `Source Han Sans CN`（思源黑体） | 苹方 → 微软雅黑 → 黑体 |

## 字体说明

### HarmonyOS Sans（鸿蒙字体）
- 开发商：华为
- 协议：**SIL Open Font License 1.1**（免费商用、免费分发）
- 风格：现代、人本、易读
- 下载：https://developer.harmonyos.com
- 适用：正文

### Source Han Sans CN（思源黑体 CN）
- 开发商：Adobe + 谷歌
- 协议：**SIL Open Font License 1.1**（免费商用）
- 风格：优雅、清晰、专业
- 下载：https://github.com/adobe-fonts/source-han-sans
- 适用：标题

### FangSong（仿宋）
- Windows 系统自带的法律文书标准字体
- macOS 需单独安装 `FangSong.ttf`

## 自动 Fallback 机制

Word/WPS 打开文档时按以下顺序匹配第一个可用字体：

1. `HarmonyOS Sans`（如已安装）
2. `FangSong`（Windows 自带 / macOS 用户需装）
3. `Source Han Sans CN`（思源黑体，常见）
4. `Microsoft YaHei`（Windows 自带）
5. `PingFang SC`（macOS 自带）
6. `SimHei`（Windows 自带的黑体）

## 安装建议（用于获得最佳视觉效果）

### macOS
- 鸿蒙字体：下载 HarmonyOS Sans-SC 系列，安装到 `~/Library/Fonts/`
- 思源黑体：通常已自带或下载后安装

### Windows
- 鸿蒙字体：同上
- 仿宋 FangSong：Windows 自带，无需额外安装

## 文件说明

- 模板中嵌入了字体名称，无须打包字体文件（节省 skill 体积）
- 模板生成的 .docx 在 Linux 系统打开会使用 LibreOffice 替换字体
- 字体文件本身**未**打入 skill，避免污染仓库
