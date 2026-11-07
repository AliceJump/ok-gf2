"""断线弹窗后方可见主页，不代表当前会话仍可继续执行日常。"""

import re
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from tests.TestActivityNavigation import method


class HomeConnectionTest(unittest.TestCase):
    def home_screen(self, dialog=""):
        check = method("src/core/BaseGfTask.py", "is_main")
        check.__globals__["fL"] = SimpleNamespace(dog_icon="dog", message_icon="message")
        task = Mock()
        task.find_one.return_value = None

        def read(*, match, **kwargs):
            if isinstance(match, list):
                return [SimpleNamespace(name=name) for name in ("整备室", "活动层", "招募")]
            if isinstance(match, re.Pattern) and match.search(dialog):
                return [SimpleNamespace(name=dialog)]
            return []

        task.ocr.side_effect = read
        task.is_main = lambda **kwargs: check(task, **kwargs)
        task.wait_until.side_effect = lambda predicate, **kwargs: predicate()
        return task

    def test_disconnect_overlay_is_not_a_usable_home(self):
        task = self.home_screen("重连失败，即将返回登录界面")
        ensure_main = method("src/core/BaseGfTask.py", "ensure_main")
        with self.assertRaisesRegex(RuntimeError, "重连失败"):
            ensure_main(task)
        task.click.assert_not_called()
        task.back.assert_not_called()

    def test_normal_home_is_still_accepted(self):
        self.assertTrue(self.home_screen().is_main())


if __name__ == "__main__":
    unittest.main()
