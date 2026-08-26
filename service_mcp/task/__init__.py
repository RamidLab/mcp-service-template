"""通用后台任务包。

- TaskManager：任务生命周期管理（状态 / 进度 / 结果 / 取消）
- TaskScheduler：按 cron 表达式周期性执行任务（runner 由调用方注入）

业务只需提供 runner 协程 `(task_id) -> awaitable`，即可接入后台任务与定时任务。
"""

from service_mcp.task.manager import Task, TaskManager, TaskStatus, TaskType
from service_mcp.task.scheduler import TaskScheduler


__all__ = ["Task", "TaskManager", "TaskScheduler", "TaskStatus", "TaskType"]
