import unittest
from src.tasks.DailyTaskRunner import DailyTaskRunner
from src.tasks.daily_summary import build_summary_lines


class Task:
    name = '一键日常'
    config = {'巡录': True, '后续任务': True}
    def __init__(self):
        self.logs, self.infos, self.screenshots = [], {}, []
    def tr(self, text): return text
    def log_info(self, text, **kwargs): self.logs.append(text)
    def info_set(self, key, value): self.infos[key] = value
    def ensure_main(self, **kwargs): pass
    def screenshot(self, name): self.screenshots.append(name)


class UncertainSummaryTest(unittest.TestCase):
    def test_uncertain_not_success_or_failure_and_next_task_runs(self):
        task = Task()
        runner = DailyTaskRunner(task, [('巡录', lambda: '待核查'), ('后续任务', lambda: True)], publish_info=True)
        runner.run()
        self.assertEqual('待核查', runner.final_summary['status'])
        self.assertEqual(['巡录'], runner.task_status['uncertain'])
        self.assertEqual(['后续任务'], runner.task_status['success'])
        self.assertEqual([], runner.task_status['failed'])
        self.assertEqual(['巡录'], task.infos['待核查的任务列表'])
        self.assertIn('DailyTask_Uncertain_巡录', task.screenshots)
        text = '\n'.join(build_summary_lines(task, runner.final_summary))
        self.assertIn('待核查任务:', text)
        self.assertIn('总任务数: 2', text)
        self.assertNotIn('所有任务执行成功', text)
        self.assertNotIn('日常完成!', '\n'.join(task.logs))

    def test_uncertainty_survives_later_successful_round(self):
        task = Task()
        results = iter(['待核查', True])
        runner = DailyTaskRunner(task, [('巡录', lambda: next(results))])
        runner.run(repeat_times=2)
        self.assertEqual('待核查', runner.final_summary['status'])
        self.assertEqual([(1, ['巡录'])], runner.final_summary['all_uncertain_tasks'])
        self.assertEqual([], runner.final_summary['per_round'][1]['uncertain'])
        self.assertNotIn('所有任务均成功完成!', task.logs)

    def test_failure_is_preserved_alongside_uncertainty(self):
        task = Task()
        runner = DailyTaskRunner(task, [('巡录', lambda: '待核查'), ('后续任务', lambda: False)])
        runner.run()
        self.assertEqual('部分失败', runner.final_summary['status'])
        self.assertEqual(['后续任务'], runner.task_status['failed'])
        self.assertEqual(['巡录'], runner.task_status['uncertain'])

    def test_exception_still_propagates(self):
        task = Task()
        def fail(): raise RuntimeError('broken')
        runner = DailyTaskRunner(task, [('巡录', lambda: '待核查'), ('后续任务', fail)])
        with self.assertRaisesRegex(RuntimeError, 'broken'):
            runner.run()
        self.assertEqual('异常结束', runner.final_summary['status'])
        self.assertEqual(['巡录'], runner.final_summary['per_round'][0]['uncertain'])
