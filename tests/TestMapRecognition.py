import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from ok import Box

from src.core.BaseGfTask import map_re
from src.tasks.ClearMapTask import ClearMapTask
from src.tasks.map_recognition import MapRecognizer, extract_map_name, same_map_location, stable_map_names


def detected(text, x=500, y=300, width=100, confidence=0.99):
    """构造带多边形、文本和置信度的 OCR 引擎返回项。"""
    return [[x, y], [x + width, y], [x + width, y + 30], [x, y + 30]], (text, confidence)


class TestMapName(unittest.TestCase):
    def test_complete_names_and_decorations(self):
        """兼容星级装饰、全角字符、前缀与普通章节编号。"""
        for raw, expected in [
            ("***KA-1-5", "KA-1-5"),
            ("米米米AA-1-4", "AA-1-4"),
            ("SF-1-12", "SF-1-12"),
            (" ia － 1 — 4 * ", "IA-1-4"),
            ("ＹＡ－１－２", "YA-1-2"),
            ("IF-1-3", "IF-1-3"),
            ("LS-1-1", "LS-1-1"),
            ("1-2", "1-2"),
            ("H1-2", "H-1-2"),
            ("N-10-12", "N-10-12"),
            ("before_one_SF-1-1", "SF-1-1"),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(extract_map_name(raw), expected)

    def test_rejects_truncation_serial_numbers_and_multiple_labels(self):
        """拒绝截断编号、序列号和包含多个关卡的歧义文本。"""
        for raw in [
            None,
            "",
            "-1-2",
            "- 1 - 2",
            "SA-1-126",
            "SA-123-1",
            "ABC-1-2",
            "//D492-414-472",
            "21/51",
            "25040",
            "SA-1-1 SA-1-2",
        ]:
            with self.subTest(raw=raw):
                self.assertIsNone(extract_map_name(raw))


class TestMapRecognizer(unittest.TestCase):
    def setUp(self):
        """准备标准 1080p 空白画面，避免测试依赖游戏截图。"""
        self.frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    def recognizer(self, *responses):
        """注入按顺序返回指定识别结果的模拟 OCR 引擎。"""
        engine = Mock()
        engine.ocr.side_effect = [[response] for response in responses]
        return MapRecognizer(engine), engine

    def test_original_image_handles_black_text_and_star_prefix(self):
        """原图已识别完整编号时保留结果，且无需颜色过滤。"""
        recognizer, engine = self.recognizer([detected("YA-1-2"), detected("***KA-1-5", x=100)])
        boxes = recognizer.recognize(self.frame)
        self.assertEqual([box.name for box in boxes], ["KA-1-5", "YA-1-2"])
        self.assertEqual(boxes[1].y, 400)
        self.assertEqual(engine.ocr.call_count, 1)
        self.assertEqual(engine.ocr.call_args.args[0].shape, (880, 1920, 3))

    def test_engine_is_created_lazily_with_full_detection_size(self):
        """独立引擎仅在首次访问时创建，并采用完整检测尺寸。"""
        recognizer = MapRecognizer()
        with patch("onnxocr.onnx_paddleocr.ONNXPaddleOcr") as create:
            engine = recognizer.engine
            self.assertIs(recognizer.engine, engine)
            create.assert_called_once_with(
                use_angle_cls=False, use_openvino=True, use_npu=False, det_limit_side_len=1920
            )

    def test_filtered_conflict_cannot_shorten_original_number(self):
        """补充过滤结果时不可缩短原图识别出的完整编号。"""
        recognizer, _ = self.recognizer(
            [detected("SA-1-12", confidence=0.75)], [detected("SA-1-1"), detected("SZ-1-5", x=900)]
        )
        self.assertEqual([box.name for box in recognizer.recognize(self.frame)], ["SA-1-12", "SZ-1-5"])

    def test_filtered_prefix_extension_cannot_invent_a_digit(self):
        """低置信度不等于截断，过滤结果不能擅自给合法编号补位。"""
        recognizer, _ = self.recognizer([detected("SA-1-2", confidence=0.75)], [detected("SA-1-23")])
        self.assertEqual([box.name for box in recognizer.recognize(self.frame)], ["SA-1-2"])

    def test_720p_confident_original_survives_longer_filtered_prefix(self):
        """低分辨率的补识别也不能覆盖原图的高置信度编号。"""
        recognizer, _ = self.recognizer([detected("SA-1-2")], [detected("SA-1-23")])
        boxes = recognizer.recognize(np.zeros((720, 1280, 3), dtype=np.uint8))
        self.assertEqual([box.name for box in boxes], ["SA-1-2"])

    def test_star_and_name_boxes_at_same_location_do_not_duplicate(self):
        """包含星级的大框与其内部编号框只保留一份。"""
        recognizer, _ = self.recognizer(
            [detected("***KA-1-5", x=200, width=220, confidence=0.75)],
            [detected("KA-1-5", x=320, width=100)],
        )
        self.assertEqual(len(recognizer.recognize(self.frame)), 1)

    def test_gray_fallback_when_original_is_empty(self):
        """原图没有编号时采用高置信度的颜色过滤结果。"""
        recognizer, _ = self.recognizer([], [detected("LS-1-1")])
        self.assertEqual(recognizer.recognize(self.frame)[0].name, "LS-1-1")

    def test_low_confidence_fallback_is_rejected(self):
        """过滤图识别置信度不足时不产生可点击的关卡框。"""
        recognizer, _ = self.recognizer([], [detected("SA-1-1", confidence=0.6)])
        self.assertEqual(recognizer.recognize(self.frame), [])

    def test_weak_raw_label_is_retried_even_when_other_labels_are_confident(self):
        """部分编号置信度低时仍补识别，不被其他可靠结果掩盖。"""
        recognizer, _ = self.recognizer(
            [detected("LS-1-1"), detected("LA-1-1", x=900, confidence=0.6)],
            [detected("LA-1-1", x=900)],
        )
        self.assertEqual([box.name for box in recognizer.recognize(self.frame)], ["LS-1-1", "LA-1-1"])

    def test_malformed_raw_number_triggers_fallback(self):
        """疑似截断的原图编号会触发过滤补识别。"""
        recognizer, _ = self.recognizer([detected("SA-1-126")], [detected("SA-1-12")])
        self.assertEqual(recognizer.recognize(self.frame)[0].name, "SA-1-12")

    def test_coordinates_are_restored_at_720p_and_1440p(self):
        """不同分辨率统一 OCR 尺寸后仍返回原屏幕坐标。"""
        for width, height in [(1280, 720), (2560, 1440)]:
            with self.subTest(width=width):
                recognizer, engine = self.recognizer([detected("SF-1-4", x=600, y=300, width=120)], [])
                box = recognizer.recognize(np.zeros((height, width, 3), dtype=np.uint8))[0]
                self.assertEqual(engine.ocr.call_args.args[0].shape[1], 1920)
                self.assertAlmostEqual(box.x, 600 * width / 1920, delta=1)
                self.assertAlmostEqual(box.y, 300 * width / 1920 + round(height * 100 / 1080), delta=1)
                self.assertAlmostEqual(box.width, 120 * width / 1920, delta=1)

    def test_empty_capture_does_not_initialize_engine(self):
        """没有截图时返回空列表，且不加载 OCR 模型。"""
        recognizer = MapRecognizer()
        self.assertEqual(recognizer.recognize(None), [])
        self.assertIsNone(recognizer._engine)

    def test_720p_supplements_labels_missing_from_partial_raw_detection(self):
        """720p 即使已有可靠编号，也补查原图漏检的其他关卡。"""
        recognizer, _ = self.recognizer([detected("LS-1-1")], [detected("LA-1-1", x=900)])
        boxes = recognizer.recognize(np.zeros((720, 1280, 3), dtype=np.uint8))
        self.assertEqual([box.name for box in boxes], ["LS-1-1", "LA-1-1"])


class TestMapStability(unittest.TestCase):
    def test_ambiguous_same_name_boxes_are_stable_in_any_order(self):
        """首个当前框需让出共有候选，才能为后一框保留唯一匹配。"""
        previous = [Box(500, 300, 100, 30, name="SA-1-1"), Box(500, 314, 100, 30, name="SA-1-1")]
        current = [Box(500, 307, 100, 30, name="SA-1-1"), Box(500, 293, 100, 30, name="SA-1-1")]
        for old_boxes in (previous, previous[::-1]):
            for new_boxes in (current, current[::-1]):
                with self.subTest(previous=old_boxes, current=new_boxes):
                    self.assertTrue(stable_map_names(old_boxes, new_boxes, 8))
                    self.assertTrue(stable_map_names(new_boxes, old_boxes, 8))

    def test_matching_cannot_reassign_a_different_name(self):
        """位置兼容也不能用另一关卡编号补足一对一匹配。"""
        previous = [Box(500, 300, 100, 30, name="SA-1-1"), Box(500, 314, 100, 30, name="SA-1-2")]
        current = [Box(500, 307, 100, 30, name="SA-1-1"), Box(500, 293, 100, 30, name="SA-1-1")]
        self.assertFalse(stable_map_names(previous, current, 8))

    def test_two_current_boxes_cannot_reuse_one_previous_box(self):
        """两个重复 OCR 框不能掩盖另一个旧框消失的事实。"""
        previous = [Box(500, 300, 100, 30, name="SA-1-1"), Box(900, 300, 100, 30, name="SA-1-1")]
        current = [Box(500, 293, 100, 30, name="SA-1-1"), Box(500, 307, 100, 30, name="SA-1-1")]
        self.assertFalse(stable_map_names(previous, current, 8))

    def test_moving_or_changed_labels_are_not_stable(self):
        """数量、编号或位置变化时拒绝稳定，小幅抖动和双空帧可通过。"""
        first = [Box(500, 300, 100, 30, name="SA-1-1")]
        for second in [[], [Box(540, 300, 100, 30, name="SA-1-1")], [Box(500, 300, 100, 30, name="SA-1-2")]]:
            self.assertFalse(stable_map_names(first, second, 8))
        self.assertTrue(stable_map_names(first, [Box(502, 301, 100, 30, name="SA-1-1")], 8))
        self.assertTrue(stable_map_names([], [], 8))

    def test_different_rows_or_adjacent_cards_are_not_merged(self):
        """不同排或相邻卡片不能被视为同一关卡位置。"""
        first = Box(500, 300, 100, 30)
        self.assertFalse(same_map_location(first, Box(500, 470, 100, 30)))
        self.assertFalse(same_map_location(first, Box(700, 300, 100, 30)))


class TestClearMapRecognition(unittest.TestCase):
    def setUp(self):
        """构造无设备任务，并替换识别引擎及等待操作。"""
        executor = SimpleNamespace(
            scene=None,
            frame=np.zeros((1080, 1920, 3), dtype=np.uint8),
            method=SimpleNamespace(width=1920, height=1080),
            device_manager=SimpleNamespace(supported_ratio=16 / 9),
        )
        self.task = ClearMapTask(executor, None)
        self.task._map_recognizer = MapRecognizer(engine=Mock())
        self.task.sleep = Mock()

    def test_legacy_ocr_options_are_retired(self):
        """旧 OCR 模式开关不再出现在任务默认配置及说明中。"""
        self.assertEqual(self.task.default_config, {})
        self.assertEqual(self.task.config_description, {})

    def test_ordinary_ui_lookup_does_not_invoke_map_engine(self):
        """普通界面文案查找沿用框架，不启动地图 OCR。"""
        self.task.find_map_names = Mock()
        boxes = [Box(500, 300, 100, 30, name="挑战")]
        self.assertEqual(self.task.find_boxes(boxes, match="挑战"), boxes)
        self.task.find_map_names.assert_not_called()

    def test_map_end_condition_keeps_popups_and_honors_boundary(self):
        """地图结束判定优先匹配弹窗文案，并遵守识别区域边界。"""
        inside = Box(500, 300, 100, 30, name="SA-1-1")
        outside = Box(500, 1000, 100, 30, name="SA-1-2")
        confirm = Box(600, 300, 80, 30, name="确认")
        self.task.find_map_names = Mock(return_value=[inside, outside])
        boundary = Box(0, 100, 1920, 880)
        self.assertEqual(self.task.find_boxes([confirm], match=[map_re, "确认"], boundary=boundary), [confirm])
        self.task.find_map_names.assert_not_called()
        self.assertEqual(self.task.find_boxes([], match=[map_re, "确认"], boundary=boundary), [inside])

    def test_reclick_is_exact_and_normalizes_retry_prefix(self):
        """重试前缀规范化后仅匹配完整编号，排除相似关卡。"""
        first = Box(500, 300, 100, 30, name="SF-1-1")
        self.task.wait_stable_map_names = Mock(return_value=[first, Box(700, 300, 100, 30, name="SF-1-12")])
        self.assertEqual(self.task.wait_stable_map_by_name("before_one_SF-1-1"), [first])
        self.task.wait_stable_map_names.assert_called_once_with(raise_if_not_found=False)

    def test_prepare_finishes_before_stability_timeout_starts(self):
        """冷启动加载模型发生在 wait_until 开始计时之前。"""
        events = []
        self.task._map_recognizer = Mock()
        self.task._map_recognizer.prepare.side_effect = lambda: events.append("prepared")

        def wait(condition, **kwargs):
            """记录等待开始时机，并返回已稳定的空地图。"""
            events.append(("wait", kwargs["time_out"]))
            return ([],)

        self.task.wait_until = wait
        self.assertEqual(self.task.wait_stable_map_names(), [])
        self.assertEqual(events, ["prepared", ("wait", 15)])

    def test_optional_reclick_timeout_is_skipped_with_warning(self):
        """附带重试的稳定等待超时不能终止已完成战斗的主流程。"""
        self.task.wait_until = Mock(return_value=None)
        self.task.log_warning = Mock()
        self.task.click = Mock()
        self.task.back = Mock()
        self.assertEqual(self.task.wait_stable_map_by_name("SF-1-1"), [])
        self.task.log_warning.assert_called_once()
        self.task.click.assert_not_called()
        self.task.back.assert_not_called()

    def test_optional_reclick_does_not_swallow_ocr_errors(self):
        """只有稳定性超时可忽略，模型或截图异常仍应向上传播。"""
        self.task.find_map_names = Mock(side_effect=RuntimeError("OCR failed"))
        self.task.wait_until = lambda condition, **kwargs: condition()
        with self.assertRaisesRegex(RuntimeError, "OCR failed"):
            self.task.wait_stable_map_by_name("SF-1-1")

    def wait_with_frames(self, frames):
        """按给定帧序列执行真实稳定性判断，序列耗尽则模拟超时。"""
        self.task.find_map_names = Mock(side_effect=frames)

        def wait(condition, **kwargs):
            """逐帧调用条件函数，返回第一个完成稳定确认的结果。"""
            for _ in frames:
                if result := condition():
                    return result
            return None

        self.task.wait_until = wait
        return self.task.wait_stable_map_names()

    def test_requires_two_matching_frames_before_using_coordinates(self):
        """移动停止后仍需连续两帧对应，才允许采用坐标。"""
        moving = [Box(500, 300, 100, 30, name="SA-1-1")]
        stopped = [Box(600, 300, 100, 30, name="SA-1-1")]
        self.assertEqual(self.wait_with_frames([moving, stopped, stopped]), stopped)
        self.assertEqual(self.task.find_map_names.call_count, 3)

    def test_same_name_boxes_with_ambiguous_matches_finish_stability_wait(self):
        """合法的交叉匹配必须在第二帧确认，不能一直等到超时。"""
        previous = [Box(500, 300, 100, 30, name="SA-1-1"), Box(500, 314, 100, 30, name="SA-1-1")]
        current = [Box(500, 307, 100, 30, name="SA-1-1"), Box(500, 293, 100, 30, name="SA-1-1")]
        self.assertEqual(self.wait_with_frames([previous, current]), current)
        self.assertEqual(self.task.find_map_names.call_count, 2)

    def test_one_empty_frame_does_not_end_map_scan(self):
        """单帧漏检不能被判作地图已清空。"""
        boxes = [Box(500, 300, 100, 30, name="SA-1-1")]
        self.assertEqual(self.wait_with_frames([boxes, [], boxes, boxes]), boxes)

    def test_continuous_movement_raises_instead_of_reporting_completion(self):
        """持续移动至超时时明确报错，不能宣告推图完成。"""
        with self.assertRaisesRegex(RuntimeError, "不稳定"):
            self.wait_with_frames([[Box(x, 300, 100, 30, name="SA-1-1")] for x in (500, 600, 700)])

    def test_missing_capture_is_not_a_stable_empty_map(self):
        """连续缺失截图时不能将空识别结果当作地图稳定。"""
        self.task.executor.frame = None
        with self.assertRaisesRegex(RuntimeError, "不稳定"):
            self.wait_with_frames([[], []])

    def test_left_to_right_sort_keeps_clicked_identity_with_its_box(self):
        """按横坐标排序时同步移动名称组，保证点击身份对应。"""
        left = Box(500, 300, 100, 30, name="SA-1-1")
        right = Box(900, 300, 100, 30, name="SA-1-2")
        self.task.wait_stable_map_names = Mock(side_effect=[[right, left], [right, left], StopIteration])
        self.task.next_frame = Mock()
        self.task.find_feature = Mock(return_value=[])
        self.task.wait_feature = Mock(return_value=None)
        self.task.wait_ocr = Mock(return_value=[])
        self.task.log_debug = Mock()
        self.task.click = Mock()
        with self.assertRaises(StopIteration):
            self.task.run()
        self.assertEqual([call.args[0].name for call in self.task.click.call_args_list], ["SA-1-1", "SA-1-2"])

    def run_stage_then_reclick(self, retry_frames):
        """保留真实稳定性判断，只替换抓帧、战斗与点击设备。"""
        initial = Box(500, 300, 100, 30, name="SF-1-1")
        challenge = Box(1400, 500, 100, 30, name="挑战")
        self.task.find_map_names = Mock(side_effect=[[initial], [initial], *retry_frames])

        def wait(condition, **kwargs):
            """在有限帧内执行稳定确认，使战后流程测试不依赖真实等待。"""
            for _ in range(10):
                if result := condition():
                    return result
            return None

        self.task.wait_until = wait
        self.task.next_frame = Mock()
        self.task.find_feature = Mock(return_value=[])
        self.task.wait_feature = Mock(return_value=None)
        self.task.wait_ocr = Mock(return_value=[Box(1400, 400, 100, 30, name="特殊奖励"), challenge])
        self.task.auto_battle = Mock()
        self.task.log_debug = Mock()
        self.task.click = Mock()
        self.task.back = Mock()
        with self.assertRaises(StopIteration):
            self.task.run()
        self.task.auto_battle.assert_called_once_with(end_match=map_re, has_dialog=True)

    def test_post_battle_reclick_waits_until_target_stops_moving(self):
        """同一编号仍在滑动时不可提前点击首次识别到的位置。"""
        retry_frames = [[Box(x, 300, 100, 30, name="SF-1-1")] for x in (600, 700, 850, 850)]
        self.run_stage_then_reclick(retry_frames)
        clicked = [call.args[0] for call in self.task.click.call_args_list]
        self.assertEqual([box[0].x if isinstance(box, list) else box.x for box in clicked], [500, 1400, 850])
        self.task.back.assert_called_once_with(after_sleep=2)

    def test_missing_stable_retry_target_does_not_click_or_back(self):
        """相似编号不能替代缺失的目标，找不到时也不能执行返回。"""
        other = [Box(800, 300, 100, 30, name="SF-1-12")]
        self.run_stage_then_reclick([other, other])
        self.assertEqual(self.task.click.call_count, 2)
        self.task.back.assert_not_called()

    def test_failed_target_disappearing_does_not_report_map_complete(self):
        """已完成一关后，丢失失败目标仍需继续枚举其他可见关卡。"""
        first = [Box(500, 300, 100, 30, name="SA-1-1")]
        failed = [Box(900, 300, 100, 30, name="SA-1-2")]
        other = [Box(1200, 300, 100, 30, name="SA-1-3")]
        self.task.wait_stable_map_names = Mock(side_effect=[first, first, failed, other, StopIteration])
        self.task.next_frame = Mock()
        self.task.find_feature = Mock(return_value=[])
        self.task.wait_feature = Mock(return_value=None)
        reward = Box(1400, 400, 100, 30, name="特殊奖励")
        self.task.wait_ocr = Mock(side_effect=[[reward, Box(1400, 500, 100, 30, name="挑战")], [reward], []])
        self.task.auto_battle = Mock()
        self.task.log_debug = Mock()
        self.task.log_info = Mock()
        self.task.click = Mock()
        self.task.back = Mock()
        with self.assertRaises(StopIteration):
            self.task.run()
        clicked = [call.args[0] for call in self.task.click.call_args_list]
        self.assertEqual(clicked[-1].name, "SA-1-3")
        self.task.log_info.assert_not_called()


if __name__ == "__main__":
    unittest.main()
