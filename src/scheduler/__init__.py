"""
任务计划程序模块

该模块包含与 Windows 任务计划程序相关的所有功能。

主要组件：
- TaskSchedulerHelper: 任务计划助手（后端逻辑）
- TaskSchedulerTab: 任务计划管理 UI（前端展示）

使用示例：
    from src.scheduler import TaskSchedulerHelper
    helper = TaskSchedulerHelper()
    success, msg = helper.create_scheduled_task(...)
"""

__all__ = ["TaskSchedulerHelper"]
