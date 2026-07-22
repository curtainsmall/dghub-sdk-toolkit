# DGHub Plugin Toolkit

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-AGPLv3-green)

[DGHub](http://dghub.top/) 插件开发辅助工具集。

## DGHub Plugin Packer — 插件打包工具

图形化桌面应用，帮助开发者创建、打包和分发 DGHub 插件。

### 功能

- **Manifest 编辑器** — 可视化编辑 manifest.json，支持 config_schema 字段编辑，JSON 预览实时更新
- **依赖打包** — 将第三方 Python 依赖打包到 `vendor/` 目录，支持自动检测、site-packages 复制、pip 下载三种方式
- **导出** — 将插件目录导出为 `.zip` 分发包，可选包含 `vendor/` 目录

### 下载

从 [Releases](https://github.com/curtainsmall/DGHub-Plugin-Toolkit/releases) 下载 `DGHubPluginPacker.exe` 直接运行。

### 使用

1. **选择插件目录** — 点击顶部"选择目录"
2. **编辑 Manifest** — 填写插件信息与配置项
3. **打包依赖** — 输入包名，点击"开始打包"
4. **导出** — 选择格式后点击"导出"

### 从源码构建

```bash
pip install -r requirements.txt

# 运行
python -m packer.main

# 打包为单文件 exe
python build_exe.py
# 产物: bin/DGHubPluginPacker.exe
```

---

## 关于

本项目基于 AGPLv3 协议开源

适用于 DGHub SDK v1
