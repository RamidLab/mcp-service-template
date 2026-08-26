"""测试通用后台任务包（task/manager.py + task/scheduler.py）"""

from datetime import datetime, timedelta

from service_mcp.task.manager import TaskManager, TaskStatus
from service_mcp.task.scheduler import TaskScheduler


async def test_create_and_get_task():
    mgr = TaskManager()
    task = await mgr.create_task({"urls": ["a"]}, name="批量")
    assert task.status == TaskStatus.PENDING
    assert task.payload == {"urls": ["a"]}
    assert (await mgr.get_task(task.id)) is task


async def test_update_status_progress_result():
    mgr = TaskManager()
    task = await mgr.create_task({}, name="t")
    await mgr.update_task_status(task.id, TaskStatus.RUNNING)
    assert task.started_at is not None

    await mgr.update_task_progress(task.id, completed=3, failed=1)
    assert task.progress["completed"] == 3
    assert task.progress["failed"] == 1

    await mgr.set_task_result(task.id, {"ok": True})
    assert task.result == {"ok": True}

    await mgr.update_task_status(task.id, TaskStatus.COMPLETED)
    assert task.completed_at is not None
    assert task.status == TaskStatus.COMPLETED


async def test_cancel_and_delete():
    mgr = TaskManager()
    task = await mgr.create_task({}, name="t")
    cancelled = await mgr.cancel_task(task.id)
    assert cancelled is not None
    assert task.status == TaskStatus.CANCELLED

    # 已结束任务不可再取消
    assert await mgr.cancel_task(task.id) is None

    assert await mgr.delete_task(task.id) is True
    assert await mgr.get_task(task.id) is None


async def test_list_and_count():
    mgr = TaskManager()
    for i in range(3):
        await mgr.create_task({"i": i}, name=f"t{i}")

    tasks = await mgr.list_tasks(limit=2)
    assert len(tasks) == 2
    # 按创建时间倒序
    assert tasks[0].name == "t2"

    tasks = await mgr.list_tasks(status=TaskStatus.PENDING)
    assert len(tasks) == 3

    counts = await mgr.get_task_count()
    assert counts == {"pending": 3}


async def test_scheduler_add_list_enable_disable_remove():
    mgr = TaskManager()
    sched = TaskScheduler(mgr, runner=_noop_runner)

    task_id = await sched.add_schedule("0 9 * * *", {"urls": []}, name="每日")
    assert task_id in mgr._tasks  # noqa: SLF001

    schedules = await sched.list_schedules()
    assert len(schedules) == 1
    assert schedules[0]["cron"] == "0 9 * * *"
    assert schedules[0]["next_run"] is not None

    assert await sched.disable_schedule(task_id) is True
    assert (await sched.list_schedules())[0]["enabled"] is False

    assert await sched.enable_schedule(task_id) is True
    assert (await sched.list_schedules())[0]["enabled"] is True

    assert await sched.remove_schedule(task_id) is True
    assert await sched.remove_schedule(task_id) is False
    assert await sched.list_schedules() == []


async def test_scheduler_invokes_runner_when_due(monkeypatch):
    calls: list[str] = []

    async def runner(task_id: str) -> None:
        calls.append(task_id)

    mgr = TaskManager()
    sched = TaskScheduler(mgr, runner)

    task_id = await sched.add_schedule("0 0 * * *", {"x": 1}, name="daily")
    # 将下次运行时间拨到过去，触发执行
    sched._scheduled_tasks[task_id].next_run = datetime.now() - timedelta(seconds=5)  # noqa: SLF001

    async def _stop_after_one(_seconds: float) -> None:
        sched._running = False  # noqa: SLF001

    monkeypatch.setattr("service_mcp.task.scheduler.asyncio.sleep", _stop_after_one)
    await sched.start()
    await sched._task  # noqa: SLF001
    assert calls == [task_id]


async def _noop_runner(task_id: str) -> None:
    """占位 runner（不在本测试中真正执行）。"""
    del task_id
