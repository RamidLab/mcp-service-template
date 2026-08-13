"""service_mcp 包初始化。

导入 path_utils 触发 load_env()，确保 .env / .env.{MCP_ENV} / .env.local 在任何
fastmcp import 之前加载，使 FASTMCP_* 环境变量能被 FastMCP Settings 正确读取。
日志初始化不在此处进行，改由 server.py 启动时显式调用 configure_logging。
"""

from service_mcp.utils.path_utils import load_env


load_env()
