# 更新日志

本文件记录项目中所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，并遵循 [语义化版本控制](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.0.1] - 2026-08-13

### Added

- 初始化通用 FastMCP + SQLAlchemy CRUD 服务模板（由基金净值 MCP 服务蒸馏）：注册表驱动 CRUD、FK code 自动解析、占位自动创建、孤儿标记、动态 Filter/Search、多传输 CLI、Docker 部署、改名脚本。
- 示例实体 Product / ProductPrice 端到端实现，演示全部核心模式（含价格冲突版本化、复合键删除）。

[0.0.1]: https://github.com/RamidLab/mcp-service-template/releases/tag/v0.0.1
