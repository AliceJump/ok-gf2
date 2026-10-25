"""战斗与班组：体力本、竞技场、兵棋推演、班组尘烟。"""

import re

import cv2

from src.core.BaseGfTask import stamina_re


def sort_characters_by_priority(chars, priority):
    """
    Sorts a list of character objects based on their 'char_name' attribute,
    according to a priority list.

    Characters whose 'char_name' attribute appears in the priority list are
    placed at the front, sorted by their order within the priority list.
    Characters not in the priority list retain their original order.

    Args:
        chars: A list of character objects, where each object has a 'char_name' attribute (string).
        priority: A list of character names (strings) representing the priority order.

    Returns:
        A new list of character objects, sorted according to the priority.  The
        original `chars` list is not modified.
    """

    priority_map = {name: index for index, name in enumerate(priority)}
    sorted_chars = []

    for i, the_char in enumerate(chars):  # Use enumerating to get the original index
        char_name = the_char.name.lower()
        if char_name in priority_map:
            sorted_chars.append((priority_map[char_name], i, the_char))  # (priority_index, original_index, char_object)
        else:
            sorted_chars.append((len(priority), i, the_char))  # (lowest_priority, original_index, char_object)

    sorted_chars.sort()  # Sort the list of tuples

    return [char_object for _, _, char_object in sorted_chars]  # Extract the character objects


class DailyBattleMixin:
    def battle(self):
        if self.config.get("自主循环"):
            self.ensure_main()
            return
        self.info_set("current_task", "battle")
        self.wait_click_ocr(
            match=re.compile("战役推进"), box=self.box.top_right, after_sleep=0.5, raise_if_not_found=True
        )
        self.wait_ocr(match=re.compile("补给作战"), box=self.box.top_right, raise_if_not_found=True)
        self.click_relative(0.78, 0.05)
        if self.is_adb():
            self.swipe_relative(0.8, 0.6, 0.5, 0.6, duration=1)
        self.sleep(1)
        remaining = 10000
        if self.config.get("刷钱本"):
            self.wait_click_ocr(match=["标准同调"], box=self.box.right, after_sleep=0.5, raise_if_not_found=True)
            remaining = self.fast_combat(battle_max=4, set_cost=20)
            self.back(after_sleep=1)
        target = self.config.get("体力本")
        cost_dict = {"深度搜索": 10, "军备解析": 10, "决策构象": 20, "定向精研": 30}
        min_stamina = cost_dict.get(target, 30)
        if remaining >= min_stamina:
            ding_xiang = self.stamina_options.index(target) >= 3
            if ding_xiang:
                target = "定向精研"
            self.wait_click_ocr(match=target, settle_time=1, after_sleep=0.5, raise_if_not_found=True, log=True)
            # if ding_xiang:
            #     self.wait_click_ocr(match=re.compile(self.config.get('体力本')),
            #                         box=self.box_of_screen(0.01, 0.21, 0.73, 0.31),
            #                         settle_time=0.5,
            #                         after_sleep=0.5, log=True,
            #                         raise_if_not_found=True)
            while remaining >= min_stamina:
                if ding_xiang:
                    remaining = self.fast_combat(plus_x=0.69, plus_y=0.59, set_cost=cost_dict[target])
                else:
                    remaining = self.fast_combat(set_cost=cost_dict.get(target))
        self.ensure_main()

    def arena(self):
        if self.config.get("自主循环"):
            self.ensure_main()
            return
        self.info_set("current_task", "arena")
        self.wait_click_ocr(
            match=re.compile("战役推进"), box=self.box.top_right, after_sleep=1, raise_if_not_found=True
        )
        self.wait_ocr(match=re.compile("补给作战"), box=self.box.top_right, raise_if_not_found=True)
        self.sleep(1)
        self.click_relative(0.89, 0.05)  # 模拟战斗
        self.wait_click_ocr(match=["实兵演习"], box=self.box.bottom, after_sleep=0.5, raise_if_not_found=True)
        self.wait_pop_up(time_out=15, count=1)
        remaining_count = self.arena_remaining()
        if remaining_count > 1:
            self.wait_click_ocr_with_pop_up("进攻", box=self.box.bottom_right)
            self.sleep(2)
            self.challenge_arena_opponent()
            self.back()
            self.sleep(1)
        # if count > 0:
        #     self.click_relative(0.34 if self.is_adb() else 0.26, 0.89, after_sleep=0.5)
        #     if not self.wait_ocr(match=['演习补给'], box=self.box.top, time_out=4):
        #         self.wait_pop_up(time_out=4)
        if self.wait_click_ocr(match=["周期奖励"], box=self.box.left, after_sleep=1, raise_if_not_found=True):
            self.wait_click_ocr(match=[re.compile("键领取")], after_sleep=1, raise_if_not_found=False)
        self.ensure_main()

    def arena_remaining(self):
        return int(self.ocr(0.89, 0.01, 0.99, 0.1, match=stamina_re)[0].name.split("/")[0])

    def challenge_arena_opponent(self):
        challenged = 0
        waited_pop_up = False
        while True:
            remaining_count = self.arena_remaining()
            self.log_info(f"challenge_arena_opponent remaining_count {remaining_count}")
            if remaining_count <= 1:
                self.log_info(f"challenge arena complete {remaining_count}")
                break
            boxes = self.ocr(0, 0.51, 0.94, 0.59, match=re.compile(r"^[1-9]\d*$"))
            if len(boxes) < 3:
                if not waited_pop_up:
                    waited_pop_up = True
                    self.wait_pop_up(time_out=15) and self.wait_pop_up(time_out=15) and self.wait_pop_up(time_out=15)
                    continue
                else:
                    raise Exception("找不到五个演习对手")
            self.log_info(f"arena opponents {boxes}")
            for box in boxes:
                if remaining_count - challenged <= 1:
                    self.log_info(f"challenged enough return {remaining_count} {challenged}")
                    return challenged
                if int(box.name) < 5000:
                    search_success = box.copy()
                    search_success.width = self.width_of_screen(0.17)
                    search_success.height = self.height_of_screen(0.15)
                    search_success.y -= search_success.height
                    if not self.ocr(match=re.compile("挑战"), box=search_success, log=True):
                        self.log_info(f"challenge opponent {box.name}")
                        self.click(box)
                        self.wait_click_ocr(
                            match=["进攻"], box=self.box.bottom_right, after_sleep=0.5, raise_if_not_found=True
                        )
                        self.auto_battle(end_match="刷新")
                        self.sleep(3)
                        challenged += 1
                        continue
            if self.ocr(match=["刷新消耗"], box=self.box.bottom_right):
                self.log_info("no refresh count remains")
                return challenged
            self.wait_click_ocr(match="刷新", box=self.box.bottom_right, after_sleep=2, raise_if_not_found=True)
        return challenged

    def bingqi(self):
        if self.config.get("自主循环"):
            self.ensure_main()
            return
        self.info_set("current_task", "bingqi")
        self.wait_click_ocr(
            match=re.compile("战役推进"), box=self.box.top_right, after_sleep=1, raise_if_not_found=True
        )
        self.wait_ocr(match=re.compile("补给作战"), box=self.box.top_right, raise_if_not_found=True)
        self.sleep(1)
        self.click_relative(0.90, 0.05, after_sleep=0.95)  # 补给
        self.click_relative(0.98, 0.49, after_sleep=0.52)
        self.wait_ocr(
            match="防御阵容",
            box=self.box.right,
            time_out=30,
            post_action=lambda: self.click_relative(0.5, 0.5, after_sleep=2),
        )
        while self.find_top_right_count():
            self.info_incr("bingqi")
            self.wait_click_ocr(match=["匹配"], box=self.box.bottom, after_sleep=0.5, raise_if_not_found=True)
            self.auto_battle(end_match="匹配")
            self.sleep(2)
        self.ensure_main()

    def guild(self):
        """执行班组要务和尘烟，助战失败时返回主页并报告失败。"""
        self.info_set("current_task", "guild")
        if result := self.wait_ocr(match=["班组"], box=self.box._group, raise_if_not_found=True):
            self.click_box_by_match_position(result, "班组", after_sleep=2)
            self.wait_click_ocr(match=["要务"], box=self.box.bottom_right, after_sleep=0.5, settle_time=2)
            result = self.wait_ocr(
                match=["开始作战", "每日要务已完成"], box=self.box.bottom_right, raise_if_not_found=True, log=True
            )
            if result[0].name == "开始作战":
                self.click(result)
                self.auto_battle()
                self.wait_ocr(
                    match=["开始作战", "每日要务已完成", "要务"], box=self.box.bottom_right, raise_if_not_found=True
                )
            else:
                self.log_info("每日要务已完成")
            self.back()
            self.sleep(1)
            if self.chenyan() is False:
                self.ensure_main()
                return False

            if not self._claim_guild_supply():
                self.ensure_main()
                return False
            self.back()
            self.sleep(1)
        self.ensure_main()

    def _guild_supply_status(self):
        """确认补给列表，并结合按钮文字与颜色判断是否仍有奖励。"""
        if not self.ocr(match=["分配中", "已分配"], box=self.box.top_right):
            return None
        individual = self.ocr(match=re.compile(r"^\s*领取\s*$"), box=self.box_of_screen(0.82, 0.20, 0.98, 0.87))
        bulk = self.ocr(match="领取全部", box=self.box.bottom_right)
        frame = self.frame
        if frame is None or frame.size == 0:
            return None
        height, width = frame.shape[:2]
        buttons = frame[int(height * 0.20) : int(height * 0.87), int(width * 0.86) : int(width * 0.95), :3]
        footer = frame[int(height * 0.89) : int(height * 0.94), int(width * 0.79) : int(width * 0.95), :3]
        if not buttons.size or not footer.size:
            return None
        green = (
            (buttons[:, :, 1] > 100)
            & (buttons[:, :, 1] > buttons[:, :, 2] * 1.15)
            & (buttons[:, :, 1] > buttons[:, :, 0] * 1.1)
        )
        yellow = (footer[:, :, 2] > 170) & (footer[:, :, 1] > 110) & (footer[:, :, 0] < 120)
        pending = bool(individual) or bool(bulk) or yellow.mean() > 0.10
        if not pending and green.mean() < 0.03:
            return None
        return {"pending": pending, "individual": individual, "bulk": bulk}

    def _claim_guild_supply(self):
        """领取后重新核对列表，批量点击无效时尝试单项，最多五次。"""
        self.info_set("班组补给", "检查中")
        self.wait_click_ocr(match=["补给"], box=self.box.bottom_right, time_out=3, after_sleep=0.5)
        attempted = False
        for attempt in range(5):
            status = self.wait_until(self._guild_supply_status, time_out=3, settle_time=0.3)
            if status is None:
                break
            if not status["pending"]:
                self.info_set("班组补给", "领取已确认" if attempted else "已领取，无可领取补给")
                return True
            target = status["individual"] if attempt and status["individual"] else status["bulk"]
            if not target:
                target = status["individual"]
            if not target:
                break
            self.click_box(target, after_sleep=0.5)
            attempted = True
            if self.wait_ocr(match=["获得道具", "点击空白处关闭"], time_out=3, raise_if_not_found=False):
                self.back(after_sleep=0.5)
            self.next_frame()
            confirmed = self.wait_until(
                lambda: (current := self._guild_supply_status()) and not current["pending"],
                time_out=2,
                settle_time=0.3,
            )
            if confirmed:
                self.info_set("班组补给", "领取已确认")
                return True
            self.log_warning(f"班组补给领取尚未确认，重试 {attempt + 1}/5")
        reason = "班组补给待核查：仍有可领项或未确认补给列表"
        self.info_set("班组补给", reason)
        runner = getattr(self, "daily_runner", None)
        if runner is not None:
            runner.set_task_failure(reason)
        self.screenshot("guild_supply_unconfirmed")
        return False

    def chenyan(self):
        """按当前剩余票数执行尘烟，每次作战后重新读取次数。"""
        if not self.config.get("尘烟"):
            return True

        def failed(reason):
            """记录失败原因并保留现场，向调用者返回明确失败。"""
            self.log_warning(f"尘烟未完成：{reason}")
            self.info_set("尘烟前线", f"待核查：{reason}")
            runner = getattr(self, "daily_runner", None)
            if runner is not None:
                runner.set_task_failure(f"尘烟未完成：{reason}")
            self.screenshot("Chenyan_EntryOrTicketsFailed")
            return False

        end = self.wait_ocr(match=re.compile("前线"), box=self.box.bottom_right, time_out=5, log=True)
        if not end:
            return failed("未找到尘烟前线入口")
        if closed := self.wait_ocr(
            match=re.compile(r"\d+\s*(?:天|小时|分钟|秒).*后\s*开\s*启"),
            box=self.box.bottom_right,
            time_out=2,
            raise_if_not_found=False,
        ):
            reason = f"未开放：{closed[0].name}，已跳过"
            self.info_set("尘烟前线", reason)
            self.log_info(f"尘烟前线{reason}，继续班组补给")
            return True
        self.click(end, after_sleep=1)
        # 页面切换和后台截图可能延迟；先确认尘烟页，避免把其他页面的数字当成次数。
        if not self.wait_ocr(match="攻坚战", box=self.box.top_right, time_out=10, log=True):
            return failed("点击入口后未确认进入尘烟页面")
        result = self.wait_ocr(match=stamina_re, box=self.box.top_right, time_out=10, log=True)
        if not result:
            return failed("未读取到剩余挑战次数，不能按次数耗尽跳过")
        while True:
            tickets = int(result[0].name.split("/")[0])
            self.log_info(f"chenyan tickets {tickets}")
            self.info_set("chenyan tickets", tickets)
            if tickets == 0:
                self.log_info("尘烟前线已确认剩余 0 次，跳过作战")
                self.info_set("尘烟前线", "已确认剩余 0 次")
                break
            self.wait_click_ocr(match="攻坚战", box=self.box.top_right, after_sleep=0.5, raise_if_not_found=True)
            self.wait_click_ocr(match="开始作战", box=self.box.bottom_right, after_sleep=2, raise_if_not_found=True)
            if not self.choose_chenyan(tickets):
                return False
            self.sleep(2)
            result = self.wait_ocr(match=stamina_re, box=self.box.top_right, time_out=10, log=True)
            if not result:
                return failed("作战后未读取到剩余挑战次数")
        self.back(after_sleep=2)
        return True

    def _select_chenyan_attribute(self, attr):
        """切换助战属性，OCR 漏读时在确认列表后使用比例坐标。"""
        if self.wait_click_ocr(match=attr, box=self.box_of_screen(0.28, 0.24, 0.81, 0.29), time_out=2, after_sleep=1):
            return True
        # 选中页签和属性图标会被 OCR 漏读；只在确认助战列表后使用固定比例位置。
        if not self.wait_ocr(match="班组助战", box=self.box_of_screen(0.35, 0.12, 0.65, 0.24), time_out=2):
            return False
        positions = {"物理": 0.313, "燃烧": 0.405, "电导": 0.500, "冷凝": 0.592, "酸蚀": 0.684, "浊刻": 0.776}
        self.click_relative(positions[attr], 0.264, after_sleep=1)
        return True

    def _scroll_chenyan_list(self, count):
        """可取消地滚动一页；PC 临时切前台，结束后恢复窗口和鼠标。"""
        self.sleep(0.01)
        executor = getattr(self, "executor", None)
        if executor is not None and executor.paused:
            return False
        if self.is_adb():
            self.swipe_relative(0.65, 0.72 if count > 0 else 0.40, 0.65, 0.40 if count > 0 else 0.72, duration=0.3)
        else:
            interaction = getattr(executor, "interaction", None)
            scroll = getattr(interaction, "scroll", None)
            if not callable(scroll):
                raise RuntimeError("当前输入后端不支持助战列表滚动")
            x, y = int(self.width * 0.65), int(self.height * 0.60)
            scroll(x, y, -3 if count > 0 else 3)
            self.sleep(0.15)
        self.sleep(0.05)
        return True

    def _chenyan_list_snapshot(self):
        """按比例裁取卡片区域，缩小副本用于判断页面是否实际变化。"""
        frame = self.frame
        if frame is None or frame.size == 0:
            return None
        height, width = frame.shape[:2]
        cards = frame[int(height * 0.31) : int(height * 0.79), int(width * 0.18) : int(width * 0.82), :3]
        if cards.size == 0:
            return None
        return cv2.resize(cards, (256, 144), interpolation=cv2.INTER_AREA)

    def _find_chenyan_assist(self, name):
        """逐页查找指定助战，仅在文字和卡片画面都未变化时提前停止。"""
        previous = None
        previous_image = None
        for page in range(100):
            self.sleep(0.01)
            executor = getattr(self, "executor", None)
            if executor is not None and executor.paused:
                return None
            chars = self.ocr(0.18, 0.31, 0.82, 0.79)
            found = next((char for char in chars if char.name.casefold() == name.casefold()), None)
            if found is not None:
                return found
            visible = chars
            self.log_info(f"助战翻页搜索 {name} 第{page + 1}页: {[box.name for box in visible]}")
            signature = tuple((box.name, round(box.x / 10), round(box.y / 10)) for box in visible)
            image = self._chenyan_list_snapshot()
            # 同名角色可以来自不同玩家；必须同时确认卡片画面基本不变。
            # 缩图降低分辨率与采集噪声影响，忽略不超过 0.5% 的轻微变化。
            same_image = (
                previous_image is not None
                and image is not None
                and (cv2.absdiff(previous_image, image).max(axis=2) > 12).mean() <= 0.005
            )
            if previous is not None and signature == previous and same_image:
                self.log_info(f"助战列表未移动，结束搜索: {name}")
                break
            previous = signature
            previous_image = image
            if page < 99 and self._scroll_chenyan_list(1) is False:
                return None
        return None

    def _find_priority_chenyan_assist(self, name):
        """已知角色按属性查找，未录入属性的首选角色遍历属性页。"""
        attr = self.get_role_by_name(name)
        for candidate_attr in [attr] if attr else self.roles_dict:
            if not self._select_chenyan_attribute(candidate_attr):
                continue
            char = self._find_chenyan_assist(name)
            if char is not None:
                return char
        return None

    def _chenyan_candidates(self):
        """提取卡片名称，排除等级、按钮和短装饰文字。"""
        chars = self.ocr(0.18, 0.31, 0.82, 0.79)
        valid = re.compile(
            r"^(?!.*(?:[LlVv][Vv]?\.?\s*\d|等级|战力|入队|确认|确定|心\s*\d))(?=.*[A-Za-z\u4e00-\u9fff]).{2,20}$"
        )
        return [
            char
            for char in chars
            if valid.fullmatch(char.name) and (re.search(r"[\u4e00-\u9fff]", char.name) or len(char.name) >= 3)
        ]

    def _is_chenyan_list(self):
        """排除弹窗后按标题确认列表，允许属性和当前卡片同时漏读。"""
        if self.ocr(
            match=[
                "确认",
                "取消",
                re.compile("队伍中有相同角色"),
                "火控预演方案",
                "Firepower Preview",
                "Combat Effectiveness",
            ],
            box=self.box_of_screen(0.2, 0.25, 0.8, 0.78),
        ):
            return False
        return bool(self.wait_ocr(match="班组助战", box=self.box_of_screen(0.35, 0.12, 0.65, 0.24), time_out=1))

    def _restore_chenyan_list(self):
        """取消冲突或关闭详情，False 可重试，None 表示恢复失败。"""
        self.wait_click_ocr(match="取消", box=self.box_of_screen(0.28, 0.65, 0.50, 0.75), time_out=0.5, after_sleep=0.3)
        if self._is_chenyan_list():
            return False
        for _ in range(2):
            self.back(after_sleep=1)
            if self._is_chenyan_list():
                return False  # 列表已恢复，可以尝试下一位。
        self.log_error("未能返回助战列表，停止本次尘烟作战")
        return None  # 恢复失败，禁止继续使用旧列表坐标。

    def _try_chenyan_assist(self, char, duplicates):
        """尝试入队，True 成功，False 可重试，None 终止流程。"""
        self.click(char, after_sleep=1)
        join = self.wait_ocr(match=["入队", "替换"], box=self.box.bottom_right, time_out=3)
        if not join:
            self.screenshot("chenyan_join_missing")
            # 国际服详情页文字可能是英文；无论详情文字是否可识别，都返回列表。
            return self._restore_chenyan_list()
        self.click_box(join, after_sleep=1)
        result = self.wait_ocr(match=["确认", "确定"], box=self.box.bottom_right, time_out=3)
        if not result:
            self.screenshot("chenyan_confirm_missing")
            return self._restore_chenyan_list()
        if any(box.name == "确认" for box in result):
            duplicates.add(char.name)
            self.log_info(f"duplicate char {sorted(duplicates)}")
            return self._restore_chenyan_list()
        self.log_info(f"助战已入队: {char.name}")
        return True

    def _order_chenyan_candidates(self, chars):
        """容忍 OCR 行位置偏移，按从上到下、每行从左到右排序。"""
        rows = []
        for char in sorted(chars, key=lambda box: box.y + box.height / 2):
            center = char.y + char.height / 2
            if rows and abs(center - rows[-1][0]) <= max(char.height, rows[-1][1]) / 2:
                rows[-1][2].append(char)
            else:
                rows.append((center, char.height, [char]))
        return [char for _, _, row in rows for char in sorted(row, key=lambda box: box.x)]

    def choose_chenyan(self, tickets):
        """配置自有人形和可用助战，只有编队确认成功才启动作战。"""
        existing = self.ocr(box=self.box_of_screen(0.61, 0.69, 0.88, 0.83), match=re.compile(r"^\d+$"))
        for exist in existing:
            self.click_box(exist, after_sleep=0.1)
        self.click_relative(0.28, 0.35, after_sleep=0.2)
        self.click_relative(0.21, 0.64, after_sleep=0.2)
        self.click_relative(0.28, 0.35, after_sleep=0.2)
        if tickets == 2:
            self.click_relative(0.16, 0.47, after_sleep=0.2)  # 编队1
        else:
            self.click_relative(0.16, 0.56, after_sleep=0.2)  # 编队2
        x_start = 0.06
        step = (0.24 - 0.03) / 3
        for i in range(4):
            self.click_relative(x_start + step * i, 0.45, after_sleep=0.2)

        self.wait_click_ocr(
            match="助战", box=self.box.bottom_right, settle_time=1, after_sleep=1, raise_if_not_found=True
        )
        priority = [
            "OTs-14",
            "威玛西娜",
            "可露凯",
            "夏安",
            "罗蕾莱",
            "春田",
            "莱妮",
            "妮基塔",
            "玛绮朵",
            "洛贝拉",
            "托洛洛",
            "琼玖",
        ]
        selected = False
        my_chars = set()
        # 排除顶部属性/装饰区；允许国际服名称和未录入角色表的新角色。

        for name in priority:
            char = self._find_priority_chenyan_assist(name)
            if char is None:
                continue

            joined = self._try_chenyan_assist(char, my_chars)
            if joined is None:
                return False
            if joined:
                selected = True
                break
        if not selected:
            self.log_info("no priority char joined, fallback start")

            attr_order = ["物理", "酸蚀", "浊刻", "燃烧", "冷凝", "电导"]

            for attr in attr_order:
                if not self._select_chenyan_attribute(attr):
                    continue

                chars = self._order_chenyan_candidates(self._chenyan_candidates())

                for char in chars:
                    if char.name in my_chars:
                        continue

                    joined = self._try_chenyan_assist(char, my_chars)
                    if joined is None:
                        return False
                    if joined:
                        self.log_info(f"fallback joined char: {char.name}")
                        selected = True
                        break

                if selected:
                    break

        if not selected:
            self.log_error("未找到可入队的助战角色，停止本次尘烟作战")
            return False
        if not self.wait_click_ocr(match="确定", box=self.box.bottom_right, time_out=5):
            self.log_error("助战入队后未找到编队确定按钮，停止本次尘烟作战")
            return False
        self.auto_battle("开始作战", self.box.bottom_right)
        return True
