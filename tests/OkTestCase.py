"""TaskTestCase 的兼容基类。

ok.test 用模块级全局 ``ok`` 保存 OK 实例，但 ``destroy_ok()`` 只调用 ``ok.quit()``，
**不会**把全局 ``ok`` 重置为 None。于是同一个进程里只有第一个 TaskTestCase 子类会
真正执行 ``init_ok()``；后续子类因为 ``ok is not None`` 直接返回，而 device_manager
已经停在 ``close()`` 之后的状态，``capture_method`` 变成 None，
``set_image()`` 就抛 ``AttributeError: 'NoneType' object has no attribute 'set_images'``。

表现很有迷惑性：单独跑 TestMain 或 TestOcr 都能通过，但
``python -m unittest discover -s tests`` 全量跑时（TestEnglish 先执行并 quit 掉 ok）
这两个类必然 error。

也**不能**靠"重置全局 ok 再重建"来修：QApplication 是单例，实例销毁后重建会抛
``RuntimeError: Please destroy the QApplication singleton before creating a new
QApplication instance``。

所以反过来做：让 OK 实例**全程存活**，第一个测试类正常初始化，后续测试类复用同一个
实例（``init_ok()`` 会跳过创建，但 feature_set / task_executor / capture_method 都还在）。
销毁推迟到最后一个测试类跑完——否则进程会因为残留的 Qt/任务线程无法退出。
"""

import ok.test as ok_test
from ok.test.TaskTestCase import TaskTestCase

_pending = 0


class OkTestCase(TaskTestCase):
    def __init_subclass__(cls, **kwargs):
        # 测试模块在 unittest 真正 run 之前就已全部导入，所以这里能数到全部子类。
        global _pending
        super().__init_subclass__(**kwargs)
        _pending += 1

    @classmethod
    def tearDownClass(cls):
        global _pending
        _pending -= 1
        if _pending <= 0:
            # 最后一个截图驱动测试类跑完，正常销毁，让进程能退出。
            ok_test.destroy_ok()
