import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from ok import Box

from src.core.BaseGfTask import map_re
from src.tasks.ClearMapTask import ClearMapTask
from src.tasks.map_recognition import MapRecognizer, extract_map_name, same_map_location, stable_map_names


def detected(text, x=500, y=300, width=100, confidence=0.99):
    return [[x, y], [x + width, y], [x + width, y + 30], [x, y + 30]], (text, confidence)


class TestMapName(unittest.TestCase):
    def test_complete_names_and_decorations(self):
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
        self.frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    def recognizer(self, *responses):
        engine = Mock()
        engine.ocr.side_effect = [[response] for response in responses]
        return MapRecognizer(engine), engine

    def test_original_image_handles_black_text_and_star_prefix(self):
        recognizer, engine = self.recognizer([detected("YA-1-2"), detected("***KA-1-5", x=100)])
        boxes = recognizer.recognize(self.frame)
        self.assertEqual([box.name for box in boxes], ["KA-1-5", "YA-1-2"])
        self.assertEqual(boxes[1].y, 400)
        self.assertEqual(engine.ocr.call_count, 1)
        self.assertEqual(engine.ocr.call_args.args[0].shape, (880, 1920, 3))

    def test_engine_is_created_lazily_with_full_detection_size(self):
        recognizer = MapRecognizer()
        with patch("onnxocr.onnx_paddleocr.ONNXPaddleOcr") as create:
            engine = recognizer.engine
            self.assertIs(recognizer.engine, engine)
            create.assert_called_once_with(
                use_angle_cls=False, use_openvino=True, use_npu=False, det_limit_side_len=1920
            )

    def test_filtered_conflict_cannot_shorten_original_number(self):
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
        recognizer, _ = self.recognizer(
            [detected("***KA-1-5", x=200, width=220, confidence=0.75)],
            [detected("KA-1-5", x=320, width=100)],
        )
        self.assertEqual(len(recognizer.recognize(self.frame)), 1)

    def test_gray_fallback_when_original_is_empty(self):
        recognizer, _ = self.recognizer([], [detected("LS-1-1")])
        self.assertEqual(recognizer.recognize(self.frame)[0].name, "LS-1-1")

    def test_low_confidence_fallback_is_rejected(self):
        recognizer, _ = self.recognizer([], [detected("SA-1-1", confidence=0.6)])
        self.assertEqual(recognizer.recognize(self.frame), [])

    def test_weak_raw_label_is_retried_even_when_other_labels_are_confident(self):
        recognizer, _ = self.recognizer(
            [detected("LS-1-1"), detected("LA-1-1", x=900, confidence=0.6)],
            [detected("LA-1-1", x=900)],
        )
        self.assertEqual([box.name for box in recognizer.recognize(self.frame)], ["LS-1-1", "LA-1-1"])

    def test_malformed_raw_number_triggers_fallback(self):
        recognizer, _ = self.recognizer([detected("SA-1-126")], [detected("SA-1-12")])
        self.assertEqual(recognizer.recognize(self.frame)[0].name, "SA-1-12")

    def test_coordinates_are_restored_at_720p_and_1440p(self):
        for width, height in [(1280, 720), (2560, 1440)]:
            with self.subTest(width=width):
                recognizer, engine = self.recognizer([detected("SF-1-4", x=600, y=300, width=120)], [])
                box = recognizer.recognize(np.zeros((height, width, 3), dtype=np.uint8))[0]
                self.assertEqual(engine.ocr.call_args.args[0].shape[1], 1920)
                self.assertAlmostEqual(box.x, 600 * width / 1920, delta=1)
                self.assertAlmostEqual(box.y, 300 * width / 1920 + round(height * 100 / 1080), delta=1)
                self.assertAlmostEqual(box.width, 120 * width / 1920, delta=1)

    def test_empty_capture_does_not_initialize_engine(self):
        recognizer = MapRecognizer()
        self.assertEqual(recognizer.recognize(None), [])
        self.assertIsNone(recognizer._engine)

    def test_720p_supplements_labels_missing_from_partial_raw_detection(self):
        recognizer, _ = self.recognizer([detected("LS-1-1")], [detected("LA-1-1", x=900)])
        boxes = recognizer.recognize(np.zeros((720, 1280, 3), dtype=np.uint8))
        self.assertEqual([box.name for box in boxes], ["LS-1-1", "LA-1-1"])


class TestMapStability(unittest.TestCase):
    def test_two_current_boxes_cannot_reuse_one_previous_box(self):
        """两个重复 OCR 框不能掩盖另一个旧框消失的事实。"""
        previous = [Box(500, 300, 100, 30, name="SA-1-1"), Box(900, 300, 100, 30, name="SA-1-1")]
        current = [Box(500, 293, 100, 30, name="SA-1-1"), Box(500, 307, 100, 30, name="SA-1-1")]
        self.assertFalse(stable_map_names(previous, current, 8))

    def test_moving_or_changed_labels_are_not_stable(self):
        first = [Box(500, 300, 100, 30, name="SA-1-1")]
        for second in [[], [Box(540, 300, 100, 30, name="SA-1-1")], [Box(500, 300, 100, 30, name="SA-1-2")]]:
            self.assertFalse(stable_map_names(first, second, 8))
        self.assertTrue(stable_map_names(first, [Box(502, 301, 100, 30, name="SA-1-1")], 8))
        self.assertTrue(stable_map_names([], [], 8))

    def test_different_rows_or_adjacent_cards_are_not_merged(self):
        first = Box(500, 300, 100, 30)
        self.assertFalse(same_map_location(first, Box(500, 470, 100, 30)))
        self.assertFalse(same_map_location(first, Box(700, 300, 100, 30)))


class TestClearMapRecognition(unittest.TestCase):
    def setUp(self):
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
        self.assertEqual(self.task.default_config, {})
        self.assertEqual(self.task.config_description, {})

    def test_ordinary_ui_lookup_does_not_invoke_map_engine(self):
        self.task.find_map_names = Mock()
        boxes = [Box(500, 300, 100, 30, name="挑战")]
        self.assertEqual(self.task.find_boxes(boxes, match="挑战"), boxes)
        self.task.find_map_names.assert_not_called()

    def test_map_end_condition_keeps_popups_and_honors_boundary(self):
        inside = Box(500, 300, 100, 30, name="SA-1-1")
        outside = Box(500, 1000, 100, 30, name="SA-1-2")
        confirm = Box(600, 300, 80, 30, name="确认")
        self.task.find_map_names = Mock(return_value=[inside, outside])
        boundary = Box(0, 100, 1920, 880)
        self.assertEqual(self.task.find_boxes([confirm], match=[map_re, "确认"], boundary=boundary), [confirm])
        self.task.find_map_names.assert_not_called()
        self.assertEqual(self.task.find_boxes([], match=[map_re, "确认"], boundary=boundary), [inside])

    def test_reclick_is_exact_and_normalizes_retry_prefix(self):
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
        self.task.find_map_names = Mock(side_effect=frames)

        def wait(condition, **kwargs):
            for _ in frames:
                if result := condition():
                    return result
            return None

        self.task.wait_until = wait
        return self.task.wait_stable_map_names()

    def test_requires_two_matching_frames_before_using_coordinates(self):
        moving = [Box(500, 300, 100, 30, name="SA-1-1")]
        stopped = [Box(600, 300, 100, 30, name="SA-1-1")]
        self.assertEqual(self.wait_with_frames([moving, stopped, stopped]), stopped)
        self.assertEqual(self.task.find_map_names.call_count, 3)

    def test_one_empty_frame_does_not_end_map_scan(self):
        boxes = [Box(500, 300, 100, 30, name="SA-1-1")]
        self.assertEqual(self.wait_with_frames([boxes, [], boxes, boxes]), boxes)

    def test_continuous_movement_raises_instead_of_reporting_completion(self):
        with self.assertRaisesRegex(RuntimeError, "不稳定"):
            self.wait_with_frames([[Box(x, 300, 100, 30, name="SA-1-1")] for x in (500, 600, 700)])

    def test_missing_capture_is_not_a_stable_empty_map(self):
        self.task.executor.frame = None
        with self.assertRaisesRegex(RuntimeError, "不稳定"):
            self.wait_with_frames([[], []])

    def test_left_to_right_sort_keeps_clicked_identity_with_its_box(self):
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
