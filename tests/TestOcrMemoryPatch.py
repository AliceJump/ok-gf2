"""OpenVINO CPU 缓存上限补丁的回归测试；真实 OCR 用例只在装了 openvino 的环境里跑。"""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch as mock_patch

source = Path(__file__).resolve().parents[1] / "src/patches/ocr_memory_patch.py"
spec = importlib.util.spec_from_file_location("ocr_memory_patch", source)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


def fake_core_class():
    class FakeCore:
        def compile_model(self, model, device_name=None, config=None):
            return model, device_name, config

    patch.patch_core_compile_model(FakeCore)
    return FakeCore


class OcrMemoryPatchTest(unittest.TestCase):
    def test_cpu_compile_gets_cache_cap(self):
        core = fake_core_class()()
        self.assertEqual(
            core.compile_model(model="m", device_name="CPU"),
            ("m", "CPU", {patch.CACHE_CAPACITY_KEY: patch.CPU_RUNTIME_CACHE_CAPACITY}),
        )

    def test_existing_config_is_kept_and_own_cap_wins(self):
        core = fake_core_class()()
        _, _, config = core.compile_model("m", "CPU", {"A": 1, patch.CACHE_CAPACITY_KEY: 7})
        self.assertEqual(config, {"A": 1, patch.CACHE_CAPACITY_KEY: 7})

    def test_other_devices_untouched(self):
        core = fake_core_class()()
        self.assertEqual(core.compile_model(model="m", device_name="NPU"), ("m", "NPU", None))
        self.assertEqual(core.compile_model("m"), ("m", None, None))

    def test_patch_is_applied_once(self):
        cls = fake_core_class()
        patched = cls.compile_model
        patch.patch_core_compile_model(cls)
        self.assertIs(cls.compile_model, patched)

    def test_real_onnxocr_compiles_on_cpu_with_cap(self):
        try:
            import numpy as np
            import openvino
            from onnxocr.onnx_paddleocr import ONNXPaddleOcr
        except ImportError as error:
            self.skipTest(f"缺少 OCR 依赖：{error}")
        patch.install_ocr_memory_patch()
        patched = openvino.Core.compile_model
        seen = []

        def spy(self, model, device_name=None, config=None, *args, **kwargs):
            seen.append((device_name, config))
            return patched(self, model, device_name, config, *args, **kwargs)

        with mock_patch.object(openvino.Core, "compile_model", spy):
            ocr = ONNXPaddleOcr(use_angle_cls=False, use_openvino=True)
            ocr.ocr(np.full((64, 200, 3), 255, dtype=np.uint8))
        self.assertTrue(seen)
        self.assertTrue(all(device == "CPU" for device, _ in seen))


if __name__ == "__main__":
    unittest.main()
