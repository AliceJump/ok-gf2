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
        self.task.find_map_names = Mock(return_value=[first, Box(700, 300, 100, 30, name="SF-1-12")])
        self.assertEqual(self.task.find_map_by_name("before_one_SF-1-1"), [first])

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


if __name__ == "__main__":
    unittest.main()
