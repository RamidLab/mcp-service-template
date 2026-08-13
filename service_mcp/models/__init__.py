from abc import ABC, abstractmethod

from pydantic import BaseModel

from service_mcp.utils.enums import NodeStatus


class StorageConfigBase(BaseModel, ABC):
    """可复用的存储连接测试模板"""

    @abstractmethod
    def url(self) -> str:
        """返回存储连接字符串"""

    @abstractmethod
    def _do_test(self, timeout: int) -> None:
        """执行实际的存储连接测试，失败则抛出异常"""

    @abstractmethod
    def _classify_error(self, exc: Exception) -> tuple[NodeStatus, str]:
        """将存储连接异常转为状态和消息"""

    def test_connection(self, timeout: int = 5) -> tuple[bool, str, NodeStatus]:
        """测试存储连接，并更新 status"""
        try:
            self._do_test(timeout)
            return True, "", NodeStatus.Active
        except Exception as e:
            status, message = self._classify_error(e)
            return False, message, status


__all__ = [
    "StorageConfigBase",
]
