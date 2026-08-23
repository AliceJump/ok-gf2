from src.tasks.BaseGfTask import BaseGfTask
from ok import TaskDisabledException
import time
class TestStartGame(BaseGfTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "启动一次游戏,120s后自动关闭"
        self.description = "配合任务计划程序提前启动游戏,防止游戏更新/弹公告导致的后续问题"
        self.add_exit_after_config()
        self.config_description.update({
            "回到主页后等待的时间": '到达主页后停留的秒数，给游戏更新和公告弹窗留出时间'
        })
        self.default_config.update({"回到主页后等待的时间": 15, "Exit After Task": True})
        self.support_schedule_task = True
    def run(self):
        try:
            self.ensure_main(time_out=120)
            wait_time = self.config.get("回到主页后等待的时间", 15)
            self.log_info(f"成功启动游戏,等待{wait_time}s后自动关闭(可禁用)", notify=True)
            self.sleep(wait_time)
        except TaskDisabledException:
            raise
        except Exception:
            self.kill_all_related_processes()
            raise
