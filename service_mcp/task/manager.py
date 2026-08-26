"""通用后台任务管理器。

任务只承载通用元数据（状态 / 进度 / 结果 / 错误），业务载荷放在 payload 中，
实际执行由调用方注入的 runner 协程完成（见 task/scheduler.py）。

用法：
    manager = TaskManager()
    task = await manager.create_task({"urls": [...]}, name="批量任务")
    await manager.update_task_status(task.id, TaskStatus.RUNNING)
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from service_mcp.utils.log import get_logger


logger = get_logger(__name__)


class TaskStatus(str, Enum):
    """任务状态枚举。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    """任务类型枚举。"""

    SINGLE = "single"
    BATCH = "batch"
    SCHEDULED = "scheduled"


class Task(BaseModel):
    """通用后台任务（业务载荷放在 payload）。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    task_type: TaskType = TaskType.SINGLE
    status: TaskStatus = TaskStatus.PENDING
    payload: dict[str, Any] = Field(default_factory=dict, description="业务载荷")
    progress: dict[str, int] = Field(
        default_factory=lambda: {"total": 0, "completed": 0, "failed": 0}
    )
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TaskManager:
    """管理任务及其生命周期（进程内内存态，asyncio.Lock 保护并发）。"""

    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._lock = asyncio.Lock()

    async def create_task(
        self,
        payload: dict[str, Any],
        name: str = "",
        task_type: TaskType = TaskType.SINGLE,
    ) -> Task:
        """创建新任务。"""
        async with self._lock:
            task = Task(
                name=name or f"Task-{len(self._tasks) + 1}",
                task_type=task_type,
                payload=payload,
            )
            self._tasks[task.id] = task
            logger.info(f"Created task {task.id}: {task.name}")
            return task

    async def get_task(self, task_id: str) -> Task | None:
        """按 ID 获取任务。"""
        return self._tasks.get(task_id)

    async def list_tasks(
        self,
        status: TaskStatus | None = None,
        task_type: TaskType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        """列出任务（按创建时间倒序），支持状态/类型过滤。"""
        tasks = list(self._tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]
        if task_type:
            tasks = [t for t in tasks if t.task_type == task_type]

        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[offset : offset + limit]

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error: str | None = None,
    ) -> Task | None:
        """更新任务状态。"""
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            task.status = status
            if status == TaskStatus.RUNNING:
                task.started_at = datetime.now()
            elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                task.completed_at = datetime.now()
            if error:
                task.error = error

            return task

    async def update_task_progress(
        self,
        task_id: str,
        completed: int,
        failed: int,
    ) -> Task | None:
        """更新任务进度。"""
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            task.progress["completed"] = completed
            task.progress["failed"] = failed
            return task

    async def set_task_result(
        self,
        task_id: str,
        result: dict[str, Any],
    ) -> Task | None:
        """设置任务结果。"""
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            task.result = result
            return task

    async def cancel_task(self, task_id: str) -> Task | None:
        """取消 pending/running 状态的任务。"""
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now()
                return task

            return None

    async def delete_task(self, task_id: str) -> bool:
        """删除任务。"""
        async with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False

    async def get_task_count(self) -> dict[str, int]:
        """按状态统计任务数。"""
        counts: dict[str, int] = {}
        for task in self._tasks.values():
            counts[task.status.value] = counts.get(task.status.value, 0) + 1
        return counts
