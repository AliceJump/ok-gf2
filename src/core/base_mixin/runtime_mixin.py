"""模板匹配（特征识别）入口的重写。

移植自 ok-end-field 的 ``src/core/base_mixin/runtime_mixin.py``。

ok-end-field 的 ``RuntimeMixin`` 里还包含危险态检测、滚轮、按键、模型加载等能力，
ok-gf2 目前没有对应设施（无 ``src/yolo``、``global_config_store``、``KeyConfig``），
因此本次只迁移与模板匹配相关的部分：``find_feature`` / ``find_one`` /
``get_feature_by_resolution``。

与 ok-end-field 的差异（都是适配 ok-gf2 现状，语义不变）：

1. ``esc`` 白色掩码分支：ok-end-field 直接写 ``fL.esc``；ok-gf2 的 ``FeatureList``
   目前没有 ``esc``，改为用 ``getattr`` 探测，缺失时整条分支跳过。
2. 分辨率后缀：ok-gf2 的特征资源目前只有无后缀一种，
   ``get_feature_by_resolution`` 会回落到原名；查找顺序、缓存键与报错语义与
   ok-end-field 完全一致，后续补 ``_2k`` / ``_4k`` 资源即可自动生效。
3. 转发父类改用关键字参数（ok-end-field 用位置参数），避免框架签名调整时错位。
"""

import cv2

from src.data.FeatureList import FeatureList as fL
from src.image.hsv_config import HSVRange as hR

feature_values = [f.value for f in fL]

# ok-gf2 的 FeatureList 暂无 esc；缺失时跳过「esc 用白色掩码」这条分支。
_ESC_FEATURE = getattr(fL, "esc", None)


class RuntimeMixin:
    """视觉识别入口：特征名按分辨率适配，并提供 ``feature=`` 别名。"""

    def get_feature_by_resolution(self, base_name: str):
        """
        根据当前分辨率选择最合适的资源后缀。

        Args:
            base_name: 资源基础名称（通常是 ``FeatureList`` 成员或字符串）。

        Returns:
            str: 匹配到的资源名称；没有带后缀的变体时返回 ``base_name`` 本身。

        Raises:
            AttributeError: 当没有任何可用资源时抛出。
        """
        cache_key = (base_name, self.width)

        if not hasattr(self, "_feature_cache"):
            self._feature_cache = {}

        if cache_key in self._feature_cache:
            return self._feature_cache[cache_key]

        if self.width >= 3800:
            suffixes = ("_4k", "_2k", "")
        elif self.width >= 2500:
            suffixes = ("_2k", "_4k", "")
        else:
            suffixes = ("", "_2k", "_4k")

        for suffix in suffixes:
            feature_name = base_name + suffix
            if feature_name in feature_values:
                self._feature_cache[cache_key] = feature_name
                return feature_name

        raise AttributeError(f"未找到任何可用资源: {base_name}")

    def find_feature(
        self,
        feature_name=None,
        horizontal_variance=0,
        vertical_variance=0,
        threshold=0,
        use_gray_scale=False,
        x=-1,
        y=-1,
        to_x=-1,
        to_y=-1,
        width=-1,
        height=-1,
        box=None,
        canny_lower=0,
        canny_higher=0,
        frame_processor=None,
        template=None,
        match_method=cv2.TM_CCOEFF_NORMED,
        screenshot=False,
        mask_function=None,
        frame=None,
        limit=0,
        target_height=0,
        feature=None,
    ):
        """
        按当前分辨率映射后执行特征识别。

        Args:
            feature_name: 特征名称或名称列表；``feature`` 是其别名。
            horizontal_variance: 水平容差。
            vertical_variance: 垂直容差。
            threshold: 匹配阈值。
            use_gray_scale: 是否使用灰度图。
            x: 区域左上角 X 坐标。
            y: 区域左上角 Y 坐标。
            to_x: 区域右下角 X 坐标。
            to_y: 区域右下角 Y 坐标。
            width: 识别区域宽度。
            height: 识别区域高度。
            box: 识别框。
            canny_lower: Canny 下限。
            canny_higher: Canny 上限。
            frame_processor: 额外帧处理器。
            template: 自定义模板。
            match_method: 模板匹配方法。
            screenshot: 是否截图后识别。
            mask_function: 掩码函数。
            frame: 输入帧。
            limit: 返回数量限制。
            target_height: 目标缩放高度。
            feature: ``feature_name`` 的兼容别名。

        Returns:
            list: 特征识别结果列表。
        """
        if feature is not None and feature_name is None:
            feature_name = feature
        if not feature_name:
            raise ValueError("必须提供 feature_name 或 feature 参数")
        if _ESC_FEATURE is not None and _ESC_FEATURE in feature_name:
            mask_function = self.make_hsv_isolator(hR.WHITE, invert=False)
        if isinstance(feature_name, (list, tuple)):
            feature_name = [self.get_feature_by_resolution(name) for name in feature_name]
        else:
            feature_name = self.get_feature_by_resolution(feature_name)
        return super().find_feature(
            feature_name=feature_name,
            horizontal_variance=horizontal_variance,
            vertical_variance=vertical_variance,
            threshold=threshold,
            use_gray_scale=use_gray_scale,
            x=x,
            y=y,
            to_x=to_x,
            to_y=to_y,
            width=width,
            height=height,
            box=box,
            canny_lower=canny_lower,
            canny_higher=canny_higher,
            frame_processor=frame_processor,
            template=template,
            match_method=match_method,
            screenshot=screenshot,
            mask_function=mask_function,
            frame=frame,
            limit=limit,
            target_height=target_height,
        )

    def find_one(
        self,
        feature_name=None,
        horizontal_variance=0,
        vertical_variance=0,
        threshold=0,
        use_gray_scale=False,
        box=None,
        canny_lower=0,
        canny_higher=0,
        frame_processor=None,
        template=None,
        mask_function=None,
        frame=None,
        match_method=cv2.TM_CCOEFF_NORMED,
        screenshot=False,
        limit=1,
        target_height=0,
        feature=None,
    ):
        """
        按当前分辨率映射后执行单个特征识别。

        分辨率适配由 ``find_feature`` 完成（框架的 ``find_one`` 会回调 ``self.find_feature``），
        这里只负责 ``feature`` 别名与 ``feature`` / ``feature_name`` 的互斥校验。

        Args:
            feature_name: 特征名称。
            horizontal_variance: 水平容差。
            vertical_variance: 垂直容差。
            threshold: 匹配阈值。
            use_gray_scale: 是否使用灰度图。
            box: 识别框。
            canny_lower: Canny 下限。
            canny_higher: Canny 上限。
            frame_processor: 额外帧处理器。
            template: 自定义模板。
            mask_function: 掩码函数。
            frame: 输入帧。
            match_method: 模板匹配方法。
            screenshot: 是否截图后识别。
            limit: 返回数量限制。
            target_height: 目标缩放高度。
            feature: ``feature_name`` 的兼容别名。

        Returns:
            Box: 置信度最高的匹配框；未匹配到时返回 None。
        """
        if feature is not None and feature_name is not None:
            raise ValueError("只能提供 feature 或 feature_name 中的一个参数，不能同时提供两者")
        if feature is None and feature_name is None:
            raise ValueError("必须提供 feature 或 feature_name 中的一个参数")

        if feature is not None:
            feature_name = feature
        return super().find_one(
            feature_name=feature_name,
            horizontal_variance=horizontal_variance,
            vertical_variance=vertical_variance,
            threshold=threshold,
            use_gray_scale=use_gray_scale,
            box=box,
            canny_lower=canny_lower,
            canny_higher=canny_higher,
            frame_processor=frame_processor,
            template=template,
            mask_function=mask_function,
            frame=frame,
            match_method=match_method,
            screenshot=screenshot,
            limit=limit,
            target_height=target_height,
        )
