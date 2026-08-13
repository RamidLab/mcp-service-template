import os

import tomli_w

from service_mcp.config import (
    MCPSettings,
    get_settings,
    setup_settings,
    store_settings,
)
from service_mcp.models.schemas import CacheConfig, DatabaseConfig


class TestMCPSettings:
    """测试 MCPSettings 配置类"""

    def test_default_values(self, mock_config_path):
        """测试默认值：无配置时使用默认值，且验证器添加默认数据库和缓存"""
        settings = MCPSettings()
        assert settings.timezone == "Asia/Shanghai"
        assert settings.default_currency == "CNY"
        # 验证器应自动添加 default 条目
        assert "default" in settings.databases
        assert isinstance(settings.databases["default"], DatabaseConfig)
        assert "default" in settings.caches
        assert isinstance(settings.caches["default"], CacheConfig)

    def test_env_var_loading(self, mock_config_path, monkeypatch):
        if mock_config_path.exists():
            mock_config_path.unlink()
        """测试环境变量加载：MCP_TIMEZONE, MCP_DEFAULT_CURRENCY, 嵌套变量使用真实字段"""
        monkeypatch.setenv("MCP_TIMEZONE", "America/New_York")
        monkeypatch.setenv("MCP_DEFAULT_CURRENCY", "USD")
        monkeypatch.setenv("MCP_DATABASES__default__DB_TYPE", "postgresql")
        monkeypatch.setenv("MCP_DATABASES__default__DB_HOST", "localhost")
        monkeypatch.setenv("MCP_DATABASES__default__DB_PORT", "5432")
        monkeypatch.setenv("MCP_CACHES__default__CACHE_TYPE", "redis")
        monkeypatch.setenv("MCP_CACHES__default__TTL_SECONDS", "199")

        settings = MCPSettings()
        assert settings.timezone == "America/New_York"
        assert settings.default_currency == "USD"
        # 验证数据库配置字段
        assert settings.databases["default"].db_type == "postgresql"
        assert settings.databases["default"].db_host == "localhost"
        assert settings.databases["default"].db_port == 5432
        assert settings.caches["default"].ttl_seconds == 199

    def test_toml_file_loading(self, mock_config_path, monkeypatch):
        """测试从 TOML 文件加载配置（优先级高于环境变量），使用实际字段"""
        monkeypatch.setenv("MCP_CONFIG_PRIORITY", "toml_first")

        toml_data = {
            "timezone": "Europe/London",
            "default_currency": "GBP",
            "databases": {
                "default": {"db_type": "sqlite", "db_host": "test.db"},
                "replica": {"db_type": "postgresql", "db_host": "replica", "db_port": 5432},
            },
            "caches": {"default": {"cache_type": "redis", "ttl_seconds": 120, "max_size": 100}},
        }
        with open(mock_config_path, "wb") as f:
            tomli_w.dump(toml_data, f)

        settings = MCPSettings()

        assert settings.timezone == "Europe/London"
        assert settings.default_currency == "GBP"
        assert settings.databases["default"].db_type == "sqlite"
        assert settings.databases["default"].db_host == "test.db"
        assert settings.databases["replica"].db_type == "postgresql"
        assert settings.databases["replica"].db_host == "replica"
        assert settings.caches["default"].ttl_seconds == 120

    def test_toml_overrides_env(self, mock_config_path, monkeypatch):
        """TOML 文件优先级应高于环境变量"""
        monkeypatch.setenv("MCP_CONFIG_PRIORITY", "toml_first")
        # 环境变量设置
        monkeypatch.setenv("MCP_TIMEZONE", "Asia/Tokyo")
        monkeypatch.setenv("MCP_DEFAULT_CURRENCY", "JPY")
        # TOML 文件设置不同的值
        toml_data = {"timezone": "Australia/Sydney", "default_currency": "AUD"}
        with open(mock_config_path, "wb") as f:
            tomli_w.dump(toml_data, f)

        settings = MCPSettings()
        # TOML 的值应生效
        assert settings.timezone == "Australia/Sydney"
        assert settings.default_currency == "AUD"

    def test_store_creates_file(self, mock_config_path):
        """测试 store 方法生成 TOML 文件，存储实际字段"""
        settings = MCPSettings()
        # 修改一些值
        settings.timezone = "Pacific/Auckland"
        settings.default_currency = "NZD"
        # 使用实际字段构造数据库配置
        settings.databases["custom"] = DatabaseConfig(
            db_type="mysql", db_host="custom", db_port=3306
        )
        settings.store()

        assert mock_config_path.exists()
        import tomllib

        with open(mock_config_path, "rb") as f:
            saved = tomllib.load(f)
        assert saved["timezone"] == "Pacific/Auckland"
        assert saved["default_currency"] == "NZD"
        assert saved["databases"]["custom"]["db_type"] == "mysql"
        assert saved["databases"]["custom"]["db_host"] == "custom"
        assert saved["databases"]["custom"]["db_port"] == 3306

    def test_init_auto_store_when_file_missing(self, mock_config_path):
        """实例化时如果配置文件不存在，应自动调用 store() 创建文件"""
        assert not mock_config_path.exists()
        _ = MCPSettings()
        assert mock_config_path.exists()
        # 验证文件内容包含默认配置（经过验证器后的）
        import tomllib

        with open(mock_config_path, "rb") as f:
            saved = tomllib.load(f)
        assert "databases" in saved
        assert "default" in saved["databases"]
        assert "caches" in saved
        assert "default" in saved["caches"]

    def test_set_default_db_with_cache_validator(self, mock_config_path):
        """验证器应在没有数据库/缓存时添加默认值，已有时不覆盖"""
        settings = MCPSettings(
            databases={"primary": DatabaseConfig(db_type="sqlite", db_host="primary.db")},
            caches={"primary": CacheConfig(ttl_seconds=60)},
        )
        # 验证器不应覆盖已有的
        assert "primary" in settings.databases
        assert "default" not in settings.databases
        assert "primary" in settings.caches
        assert "default" not in settings.caches


class TestGlobalFunctions:
    """测试全局配置实例管理函数"""

    def test_setup_settings(self, mock_config_path):
        """setup_settings 应创建并返回新实例，更新全局 _settings"""
        settings = setup_settings()
        assert isinstance(settings, MCPSettings)
        settings2 = setup_settings()
        assert settings2 == settings

    def test_get_settings_initial_none(self, mock_config_path):
        """get_settings 在 _settings 为 None 时应自动创建实例"""
        import service_mcp.config as config_module

        config_module._settings = None  # noqa
        settings = get_settings()
        assert isinstance(settings, MCPSettings)
        # 再次调用应返回同一实例
        settings2 = get_settings()
        assert settings2 is settings

    def test_get_settings_reload(self, mock_config_path):
        """reload=True 时应重新创建实例"""
        settings1 = get_settings()
        settings1.timezone = "Custom/Zone"
        # 修改环境变量以验证新实例会重新加载
        os.environ["MCP_TIMEZONE"] = "New/Zone"
        settings2 = get_settings(reload=True)
        assert settings2 is not settings1
        assert settings2.timezone == "New/Zone"

    def test_store_settings_without_arg(self, mock_config_path):
        """store_settings(settings) 应保存指定实例到 TOML 文件"""
        settings = get_settings()
        settings.timezone = "Africa/Cairo"
        store_settings(settings)
        assert mock_config_path.exists()
        import tomllib

        with open(mock_config_path, "rb") as f:
            saved = tomllib.load(f)
        assert saved["timezone"] == "Africa/Cairo"

    def test_store_settings_with_arg(self, mock_config_path):
        """store_settings(settings) 应保存指定实例"""
        settings1 = MCPSettings()
        settings1.timezone = "America/Argentina"
        settings2 = MCPSettings()
        settings2.timezone = "Antarctica/McMurdo"
        store_settings(settings1)
        import tomllib

        with open(mock_config_path, "rb") as f:
            saved = tomllib.load(f)
        assert saved["timezone"] == "America/Argentina"
        # 再保存 settings2
        store_settings(settings2)
        with open(mock_config_path, "rb") as f:
            saved = tomllib.load(f)
        assert saved["timezone"] == "Antarctica/McMurdo"


class TestSettingsCustomisation:
    """测试自定义配置源顺序"""

    def test_source_order(self, mock_config_path, monkeypatch):
        """验证配置源顺序：TOML 文件优先于环境变量"""
        monkeypatch.setenv("MCP_CONFIG_PRIORITY", "toml_first")
        # 同时设置环境变量和 TOML 文件
        monkeypatch.setenv("MCP_TIMEZONE", "Env/Zone")
        toml_data = {"timezone": "Toml/Zone"}
        with open(mock_config_path, "wb") as f:
            tomli_w.dump(toml_data, f)

        settings = MCPSettings()
        # TOML 的值应覆盖环境变量
        assert settings.timezone == "Toml/Zone"

        # 删除 TOML 文件，应回退到环境变量
        mock_config_path.unlink()
        settings2 = MCPSettings()
        assert settings2.timezone == "Env/Zone"

    def test_env_nested_delimiter(self, mock_config_path, monkeypatch):
        """测试环境变量嵌套分隔符 __ 能正确解析嵌套字段（使用真实字段名）"""
        monkeypatch.setenv("MCP_CONFIG_PRIORITY", "env_first")
        monkeypatch.setenv("MCP_DATABASES__replica__DB_TYPE", "postgresql")
        monkeypatch.setenv("MCP_DATABASES__replica__DB_HOST", "replica")
        monkeypatch.setenv("MCP_DATABASES__replica__DB_PORT", "5432")
        monkeypatch.setenv("MCP_DATABASES__replica__DB_POOL_SIZE", "5")
        settings = MCPSettings()
        assert "replica" in settings.databases
        assert settings.databases["replica"].db_type == "postgresql"
        assert settings.databases["replica"].db_host == "replica"
        assert settings.databases["replica"].db_port == 5432
        assert settings.databases["replica"].db_pool_size == 5
