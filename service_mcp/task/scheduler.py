"""通用 cron 调度器。

用法：
    manager = TaskManager()
    scheduler = TaskScheduler(manager, runner=run_task_by_id)  # run_task_by_id: (task_id) -> awaitable
    task_id = await scheduler.add_schedule("0 9 * * *", {"urls": [...]}, name="每日任务")
    await scheduler.start()
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from service_mcp.task.manager import TaskManager, TaskType
from service_mcp.utils.cron import CronExpression
from service_mcp.utils.log import get_logger


logger = get_logger(__name__)

# runner 协议：接收 task_id，异步执行任务（可立即返回，内部自行启动后台协程）
TaskRunner = Callable[[str], Awaitable[None]]


class ScheduledTask:
    """表示一个周期性任务。"""

    def __init__(
        self,
        task_id: str,
        cron: CronExpression,
        payload: dict[str, Any],
        enabled: bool = True,
    ):
        self.task_id = task_id
        self.cron = cron
        self.payload = payload
        self.enabled = enabled
        self.last_run: datetime | None = None
        self.next_run: datetime | None = None
        self.update_next_run()

    def update_next_run(self) -> None:
        """更新下次运行时间。"""
        try:
            self.next_run = self.cron.next_run(self.last_run)
        except ValueError:
            self.next_run = None


class TaskScheduler:
    """按 cron 表达式周期性创建并执行任务。"""

    def __init__(
        self,
        task_manager: TaskManager,
        runner: TaskRunner,
    ):
        self.task_manager = task_manager
        self.runner = runner
        self._scheduled_tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    async def add_schedule(
        self,
        cron_expression: str,
        payload: dict[str, Any],
        name: str = "",
    ) -> str:
        """添加周期性任务（先登记任务，再挂到调度表），返回任务 ID。"""
        task = await self.task_manager.create_task(
            payload, name=name, task_type=TaskType.SCHEDULED
        )
        cron = CronExpression(cron_expression)
        scheduled = ScheduledTask(task_id=task.id, cron=cron, payload=payload)
        self._scheduled_tasks[task.id] = scheduled
        logger.info(f"Added scheduled task {task.id} with cron: {cron_expression}")
        return task.id

    async def remove_schedule(self, task_id: str) -> bool:
        """移除周期性任务。"""
        if task_id in self._scheduled_tasks:
            del self._scheduled_tasks[task_id]
            logger.info(f"Removed scheduled task {task_id}")
            return True
        return False

    async def enable_schedule(self, task_id: str) -> bool:
        """启用周期性任务。"""
        scheduled = self._scheduled_tasks.get(task_id)
        if scheduled:
            scheduled.enabled = True
            scheduled.update_next_run()
            return True
        return False

    async def disable_schedule(self, task_id: str) -> bool:
        """停用周期性任务。"""
        scheduled = self._scheduled_tasks.get(task_id)
        if scheduled:
            scheduled.enabled = False
            return True
        return False

    async def list_schedules(self) -> list[dict[str, Any]]:
        """列出全部周期性任务。"""
        schedules = []
        for task_id, scheduled in self._scheduled_tasks.items():
            schedules.append(
                {
                    "task_id": task_id,
                    "cron": scheduled.cron.expression,
                    "enabled": scheduled.enabled,
                    "last_run": scheduled.last_run.isoformat() if scheduled.last_run else None,
                    "next_run": scheduled.next_run.isoformat() if scheduled.next_run else None,
                    "payload": scheduled.payload,
                }
            )
        return schedules

    async def start(self) -> None:
        """启动调度循环。"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Task scheduler started")

    async def stop(self) -> None:
        """停止调度循环。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Task scheduler stopped")

    async def _run(self) -> None:
        """调度主循环。"""
        while self._running:
            now = datetime.now()

            for task_id, scheduled in list(self._scheduled_tasks.items()):
                if not scheduled.enabled:
                    continue

                if scheduled.next_run and now >= scheduled.next_run:
                    logger.info(f"Running scheduled task {task_id}")
                    scheduled.last_run = now
                    scheduled.update_next_run()

                    await self.runner(task_id)

            await asyncio.sleep(10)
