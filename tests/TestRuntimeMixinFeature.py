# Test case
"""RuntimeMixin 模板匹配入口（find_feature / find_one）的行为测试。

覆盖从 ok-end-field 移植过来的三条契约：

- ``feature=`` 是 ``feature_name=`` 的别名（ok-script 2.0.5 原生不支持，传了会 TypeError）；
- ``find_one`` 在「同时传两者」或「两者都不传」时报 ``ValueError``；
- 特征名先经 ``get_feature_by_resolution`` 做分辨率适配，再交给框架。
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.base_mixin import runtime_mixin  # noqa: E402
from src.core.base_mixin.runtime_mixin import RuntimeMixin  # noqa: E402
from src.image.hsv_config import HSVRange as hR  # noqa: E402


class FakeFramework:
    """ok-script ``FindFeature`` 的替身：记录收到的参数，``find_one`` 回调 ``self.find_feature``。"""

    def __init__(self, width=1920):
        self._width = width
        self.feature_calls = []

    @property
    def width(self):
        return self._width

    def find_feature(self, feature_name=None, **kwargs):
        self.feature_calls.append((feature_name, kwargs))
        return [f'box:{feature_name}']

    def find_one(self, feature_name=None, **kwargs):
        boxes = self.find_feature(feature_name=feature_name, **kwargs)
        return boxes[0] if boxes else None

    def make_hsv_isolator(self, ranges, invert=True, kernel_size=2):
        return ('isolator', ranges, invert, kernel_size)


class FakeTask(RuntimeMixin, FakeFramework):
    pass


class TestFeatureAlias(unittest.TestCase):
    """``feature=`` 别名与参数校验。"""

    def setUp(self):
        self.task = FakeTask()

    def test_find_feature_accepts_feature_alias(self):
        self.task.find_feature(feature='dog_icon')
        self.assertEqual(self.task.feature_calls[0][0], 'dog_icon')

    def test_find_one_accepts_feature_alias(self):
        self.assertEqual(self.task.find_one(feature='dog_icon'), 'box:dog_icon')

    def test_find_one_rejects_both_arguments(self):
        with self.assertRaises(ValueError):
            self.task.find_one('dog_icon', feature='confirm')

    def test_find_one_requires_an_argument(self):
        with self.assertRaises(ValueError):
            self.task.find_one()

    def test_find_feature_requires_an_argument(self):
        with self.assertRaises(ValueError):
            self.task.find_feature()

    def test_find_feature_rejects_empty_name(self):
        with self.assertRaises(ValueError):
            self.task.find_feature(feature_name='')

    def test_positional_arguments_still_work(self):
        """既有调用点用的是位置参数（如 BaseGfTask.is_main）。"""
        self.assertEqual(self.task.find_one('dog_icon', 0.002, 0.002, 0.5), 'box:dog_icon')

    def test_extra_kwargs_reach_the_framework(self):
        self.task.find_one('dog_icon', use_gray_scale=True)
        self.assertTrue(self.task.feature_calls[0][1]['use_gray_scale'])


class TestFeatureResolution(unittest.TestCase):
    """``get_feature_by_resolution`` 的查找顺序与缓存。"""

    def setUp(self):
        self._original_values = list(runtime_mixin.feature_values)
        self.addCleanup(self._restore_values)

    def _restore_values(self):
        runtime_mixin.feature_values[:] = self._original_values

    def _add_features(self, *names):
        runtime_mixin.feature_values.extend(names)

    def test_base_name_is_kept_when_no_suffixed_variant(self):
        self.assertEqual(FakeTask().get_feature_by_resolution('dog_icon'), 'dog_icon')

    def test_unknown_feature_raises_attribute_error(self):
        with self.assertRaises(AttributeError):
            FakeTask().get_feature_by_resolution('not_a_feature')

    def test_picks_2k_variant_on_mid_resolution(self):
        self._add_features('dog_icon_2k')
        self.assertEqual(FakeTask(width=2560).get_feature_by_resolution('dog_icon'), 'dog_icon_2k')

    def test_picks_4k_variant_on_high_resolution(self):
        self._add_features('dog_icon_2k', 'dog_icon_4k')
        self.assertEqual(FakeTask(width=3840).get_feature_by_resolution('dog_icon'), 'dog_icon_4k')

    def test_high_resolution_falls_back_to_2k_when_4k_missing(self):
        self._add_features('dog_icon_2k')
        self.assertEqual(FakeTask(width=3840).get_feature_by_resolution('dog_icon'), 'dog_icon_2k')

    def test_low_resolution_prefers_base_name(self):
        self._add_features('dog_icon_2k')
        self.assertEqual(FakeTask(width=1920).get_feature_by_resolution('dog_icon'), 'dog_icon')

    def test_result_is_cached_per_resolution(self):
        task = FakeTask(width=1920)
        task.get_feature_by_resolution('dog_icon')
        self.assertEqual(task._feature_cache[('dog_icon', 1920)], 'dog_icon')

    def test_find_feature_maps_each_item_of_a_list(self):
        self._add_features('confirm_2k')
        task = FakeTask(width=2560)
        task.find_feature(feature_name=['dog_icon', 'confirm'])
        self.assertEqual(task.feature_calls[0][0], ['dog_icon', 'confirm_2k'])

    def test_find_one_resolves_through_the_framework_find_feature(self):
        """框架的 find_one 内部回调 self.find_feature，分辨率适配只应发生一次且生效。"""
        self._add_features('dog_icon_2k')
        task = FakeTask(width=2560)
        self.assertEqual(task.find_one('dog_icon'), 'box:dog_icon_2k')


class TestEscMaskBranch(unittest.TestCase):
    """``esc`` 用白色掩码那条分支：ok-gf2 的 FeatureList 暂无 esc，缺失时应自动跳过。"""

    def setUp(self):
        self._original_values = list(runtime_mixin.feature_values)
        self.addCleanup(self._restore_values)

    def _restore_values(self):
        runtime_mixin.feature_values[:] = self._original_values

    def test_feature_list_has_no_esc_yet(self):
        self.assertIsNone(runtime_mixin._ESC_FEATURE)

    def test_branch_is_skipped_when_esc_is_absent(self):
        task = FakeTask()
        task.find_feature(feature_name='dog_icon')
        self.assertIsNone(task.feature_calls[0][1]['mask_function'])

    def test_branch_applies_white_mask_once_esc_exists(self):
        runtime_mixin.feature_values.append('esc_icon')
        task = FakeTask()
        with mock.patch.object(runtime_mixin, '_ESC_FEATURE', 'esc'):
            task.find_feature(feature_name='esc_icon')
        mask = task.feature_calls[0][1]['mask_function']
        self.assertEqual(mask, ('isolator', hR.WHITE, False, 2))

    def test_explicit_mask_function_is_overridden_by_esc_branch(self):
        runtime_mixin.feature_values.append('esc_icon')
        task = FakeTask()
        with mock.patch.object(runtime_mixin, '_ESC_FEATURE', 'esc'):
            task.find_feature(feature_name='esc_icon', mask_function='custom')
        self.assertEqual(task.feature_calls[0][1]['mask_function'], ('isolator', hR.WHITE, False, 2))


if __name__ == '__main__':
    unittest.main()
