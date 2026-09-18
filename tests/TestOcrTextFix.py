import re
import unittest
from types import SimpleNamespace

from src.patches import ocr_text_fix_patch as patch


class TestOcrTextFix(unittest.TestCase):
    """assets/ocr_fix/ocr_text_fix.json 的错字兼容（移植自 ok-end-field）。"""

    def setUp(self):
        self._saved = dict(patch._CHAR_CONFUSION)
        patch.reload_ocr_text_fix()

    def tearDown(self):
        patch._CHAR_CONFUSION = self._saved

    def test_fix_map_loaded_from_assets(self):
        fix_map = patch._load_fix_map()
        self.assertIn("鏡像冗余", fix_map)
        self.assertEqual(fix_map["鏡像冗余"], "镜像冗余")

    def test_build_char_confusion(self):
        confusion = patch._build_char_confusion({"鏡像冗余": "镜像冗余"})
        self.assertEqual(confusion.get("镜"), ("鏡",))

    def test_string_match_expands_variants(self):
        result = patch._apply_confusion_to_match("镜像冗余")
        self.assertIn("镜像冗余", result)
        self.assertIn("鏡像冗余", result)

    def test_regex_literal_is_expanded(self):
        patched = patch._apply_confusion_to_match(re.compile("^镜像冗余$"))
        self.assertTrue(patched.match("镜像冗余"))
        self.assertTrue(patched.match("鏡像冗余"))

    def test_regex_escape_and_class_are_safe(self):
        patched = patch._apply_confusion_to_match(re.compile(r"^\d+[镜鏡]像$"))
        self.assertTrue(patched.match("12镜像"))
        self.assertTrue(patched.match("12鏡像"))
        self.assertIsNone(patched.match("像冗余"))

    def test_list_match_is_flattened(self):
        result = patch._apply_confusion_to_match(["确认", "镜像冗余"])
        self.assertIn("确认", result)
        self.assertIn("鏡像冗余", result)

    def test_without_confusion_returns_original(self):
        patch._CHAR_CONFUSION = {}
        self.assertEqual(patch._apply_confusion_to_match("镜像冗余"), "镜像冗余")

    def test_installed_patch_applies_to_ocr(self):
        from ok.task.task import OCR

        patch.install_ocr_text_fix_patch()
        stub = SimpleNamespace(executor=SimpleNamespace(ocr_po_translation=None))
        result = OCR.fix_match_regex(stub, "镜像冗余")
        self.assertIn("鏡像冗余", result)


if __name__ == "__main__":
    unittest.main()
