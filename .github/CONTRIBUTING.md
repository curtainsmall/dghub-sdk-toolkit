# Contributing / 贡献指南

感谢你对 DGHub SDK Toolkit 的贡献！提交代码前请阅读以下约定。

## 分支策略

- **禁止向 `main` 发起 PR 或推送**。`main` 是受保护的发布分支，
  仅由仓库维护者从 `develop` 合并更新。指向 `main` 的 PR 会被
  修改目标分支或直接关闭。
- 所有开发工作基于 **`develop`** 分支进行，PR 也一律指向 `develop`。
- 建议从最新的 `develop` 拉出 feature 分支开发：

  ```bash
  git checkout develop
  git pull
  git branch feature/your-feature
  ```

- 开发期间若 `develop` 合入了关键修复，请尽早将其 merge 进你的
  feature 分支，避免最终合并时产生大量冲突。

## 发布流程（仅维护者）

- 发布由维护者执行：`develop` → 合并至 `main` → 推送 `v*` tag
- `v*` tag 会自动触发 GitHub Actions 构建与发布（GitHub Release + PyPI）
- 贡献者请勿创建或推送 `v*` tag

## 开发环境

- Python 3.11+
- SDK（`sdk/python/`）：使用 [uv](https://docs.astral.sh/uv/) 管理，
  运行测试：

  ```bash
  cd sdk/python
  uv run --extra test pytest
  ```

- Packer（`packer/`）：使用 [uv](https://docs.astral.sh/uv/) 管理，
  开发版启动：

  ```bash
  uv sync --project packer
  uv run --project packer python -m packer.src.main
  ```

## 提交约定

- 提交信息建议使用 Conventional Commits 风格（如 `feat(sdk): ...`、
  `fix(packer): ...`）
- SDK 公共 API 的不兼容变更需在 PR 描述中明确标注，并同步更新
  `docs/` 下的相关文档与测试
- 新功能请附带测试（`sdk/python/tests/`）
