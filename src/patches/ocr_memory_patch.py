"""限制 OpenVINO CPU 插件的按形状缓存，避免 OCR 内存随识别区域尺寸无限增长。

onnxocr 把模型按全动态形状编到 CPU 上，CPU 插件为每种新输入尺寸缓存一份编译结果，
默认上限 5000 条且不释放。识别模型的输入宽度随文字框宽高比连续变化，ok-gf2 的识别区域又多，
2026-10-22 实测桌面端几分钟就到 5.5～9GB，空闲也不回落。

实机上同一识别模型随机宽度 300 次（起点约 570MB）：不设上限 50 次就到 3.3GB 还在涨；
上限 100 稳定在约 2.1GB；上限 20 约 1.9GB；上限 0 约 1.8GB，单次耗时都在 100ms 左右。
识别结果不变，只是不常用尺寸的编译结果更早被淘汰。
"""

import logging

CPU_RUNTIME_CACHE_CAPACITY = 20
CACHE_CAPACITY_KEY = "CPU_RUNTIME_CACHE_CAPACITY"
_PATCH_MARKER = "_ok_gf2_runtime_cache_capped"


def _is_cpu(device_name):
    """判断编译目标是不是 CPU（含 CPU:0 这类写法）。"""
    return isinstance(device_name, str) and device_name.upper().startswith("CPU")


def patch_core_compile_model(core_class):
    """给 CPU 编译补上缓存上限；调用方自己设置了上限时保留调用方的值。"""
    if getattr(core_class, _PATCH_MARKER, False):
        return
    original_compile_model = core_class.compile_model

    def capped_compile_model(self, model, device_name=None, config=None, *args, **kwargs):
        if _is_cpu(device_name) and (config is None or isinstance(config, dict)):
            config = dict(config or {})
            config.setdefault(CACHE_CAPACITY_KEY, CPU_RUNTIME_CACHE_CAPACITY)
        if device_name is None and config is None:
            return original_compile_model(self, model, *args, **kwargs)
        if config is None:
            return original_compile_model(self, model, device_name, *args, **kwargs)
        return original_compile_model(self, model, device_name, config, *args, **kwargs)

    core_class.compile_model = capped_compile_model
    setattr(core_class, _PATCH_MARKER, True)


def install_ocr_memory_patch():
    """幂等安装；没有 openvino 时跳过，不影响启动。"""
    try:
        import openvino
    except Exception as error:
        logging.getLogger(__name__).info(f"未安装 openvino，跳过 OCR 缓存上限：{error}")
        return
    patch_core_compile_model(openvino.Core)
