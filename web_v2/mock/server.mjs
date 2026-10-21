// 本机联调用的假后端：模仿 ok-script Web 模式的 /api 接口形状（不含 websocket）。
//   node mock/server.mjs        → http://127.0.0.1:8765
// 配合 `npm run dev`（vite 把 /api 代理到 8765）或者直接 `npm run build` 后用 serve_web_v2.py。
import http from 'node:http';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const catalog = JSON.parse(readFileSync(path.join(here, '../public/catalog.json'), 'utf8'));

const field = (key, value, kind, extra = {}) => ({ key, value, default: value, kind, description: extra.description ?? '', options: extra.options ?? null, minimum: extra.minimum ?? null, maximum: extra.maximum ?? null, sub_config: !!extra.sub_config });

const dailyKeys = [
  ['邮件', true, 'boolean'],
  ['情报和战前补给', true, 'boolean'],
  ['闪耀星愿', false, 'boolean'],
  ['活动自律', true, 'boolean'],
  ['当前物资关卡名称', '物资关卡-5', 'text', { sub_config: true, description: '活动里要刷的物资关卡名' }],
  ['探索领取', true, 'boolean'],
  ['活动层', true, 'boolean'],
  ['喝水', '1.087-1.0-0.8', 'text', { sub_config: true, description: '饮品坐标预设，和实机一致' }],
  ['吃饭', '1.0', 'text', { sub_config: true, description: '今日已用餐会跳过' }],
  ['活动层浇花', false, 'boolean', { sub_config: true }],
  ['公共区/调度室', true, 'boolean'],
  ['自主循环', false, 'boolean', { sub_config: true, description: '开了会跳过体力本、刷钱本、竞技场' }],
  ['领任务', true, 'boolean'],
  ['购买免费礼包', true, 'boolean'],
  ['商店心愿单购买', false, 'boolean', { sub_config: true }],
  ['自动刷体力', true, 'boolean'],
  ['体力本', '标准作战-6', 'select', { sub_config: true, options: ['标准作战-1', '标准作战-2', '标准作战-3', '标准作战-4', '标准作战-5', '标准作战-6'] }],
  ['刷钱本', '关闭', 'select', { sub_config: true, options: ['关闭', '基础', '进阶'] }],
  ['竞技场', true, 'boolean'],
  ['班组', true, 'boolean'],
  ['尘烟', false, 'boolean', { sub_config: true, description: '指挥官未到 60 级自动跳过' }],
  ['尘烟买第3次', false, 'boolean', { sub_config: true, description: '免费次数用完后花 50 坍塌晶条再买一次' }],
  ['大月卡', true, 'boolean'],
  ['拂晓之光补给包奖励', '访问许可', 'select', { sub_config: true, options: ['访问许可', '标准访问许可', '算力'] }],
  ['社区每日', false, 'boolean'],
  ['用户名', '', 'text', { sub_config: true }],
  ['密码', '', 'text', { sub_config: true }],
  ['已确认启用游戏内全局自动功能', true, 'boolean', { description: '进游戏后手动开过「全局自动」才勾' }],
  ['生成汇总文件', true, 'boolean'],
  ['自动打开汇总文件', false, 'boolean', { sub_config: true }],
  ['Exit After Task', false, 'boolean'],
  ['多账户模式', false, 'boolean'],
  ['多账户独立配置', false, 'boolean', { sub_config: true }],
  ['账号列表', [], 'list', { sub_config: true, description: '每行一个账号' }],
  ['重试次数', 2, 'integer', { minimum: 0, maximum: 5 }],
];

const state = {
  status: { running: false, paused: false, starting: false, current_task: null },
  tasks: [
    { name: '一键日常', class_name: 'DailyTask', enabled: true, running: false, paused: false, trigger: false, description: '按勾选项跑一轮日常', info: { '今日已完成(含之前几次)': ['邮件', '情报和战前补给'], '今日待重试': ['竞技场'], 上次运行: '2026-10-20 05:12' }, config: dailyKeys.map((a) => field(...a)) },
    { name: '周常', class_name: 'WeeklyTask', enabled: true, running: false, trigger: false, description: '', info: {}, config: [field('首领挑战', true, 'boolean'), field('峰值推定', true, 'boolean'), field('扩编实练', false, 'boolean')] },
    { name: '推图', class_name: 'ClearMapTask', enabled: true, running: false, trigger: false, description: '停在任意关卡页面或章节选择页启动即可，先回章节起点从左到右推完未通关的关卡，推完自动进下一章', info: {}, config: [field('普通OCR', true, 'boolean', { description: '普通OCR：不做任何图像预处理，直接识别关卡名称' }), field('除杂色OCR1', true, 'boolean', { description: '除杂色OCR1（标准白色）' }), field('除杂色OCR2', true, 'boolean', { description: '除杂色OCR2（宽松白灰色）' }), field('战斗内点击自动', false, 'boolean', { description: '进入战斗后若检测到「行动结束」，自动点击右上角的自动战斗按钮' }), field('推完继续下一章', true, 'boolean', { description: '本章能推的都推完（或剩下的都没解锁）后，回章节选择页进入下一章继续推' })] },
    { name: '启动一次游戏,120s后自动关闭', class_name: 'TestStartGame', enabled: true, running: false, trigger: false, description: '配合任务计划程序提前启动游戏', info: {}, config: [field('Exit After Task', true, 'boolean'), field('回到主页后等待的时间', 15, 'integer')] },
    { name: '测试用', class_name: 'TestTask', enabled: true, running: false, trigger: false, description: '收菜', info: {}, config: [] },
    { name: '调试工具', class_name: 'DebugTask', enabled: true, running: false, trigger: false, description: '按配置点一个文字 / 按 ESC / 截图，供远程调试用', info: {}, config: [field('先回主页', false, 'boolean'), field('点击文字', '', 'text'), field('点击坐标', '', 'text'), field('按ESC次数', 0, 'integer'), field('按键', '', 'text'), field('截图并OCR', false, 'boolean')] },
    { name: 'Diagnosis', class_name: 'DiagnosisTask', enabled: true, running: false, trigger: false, description: 'Performance Test', info: {}, config: [] },
    { name: '未列出的任务', class_name: 'SomeNewTask', enabled: true, running: false, trigger: false, description: '模拟后端新加、目录里还没有的任务', info: {}, config: [field('开关', true, 'boolean')] },
    { name: '模板监控', class_name: 'TemplateMonitorTask', enabled: false, running: false, trigger: true, description: '后台监控弹窗并自动处理', info: {}, config: [field('检测间隔(秒)', 5, 'integer', { minimum: 1, maximum: 60 })] },
  ],
  settings: [
    { name: '阵容与助战', description: '所有会进部署界面的任务共用。优先级：内置默认 → 这里的全局值 → 各场景单独设置（新版界面里在各板块直接改）', fields: [
      field('编队名', '编队1', 'text', { description: '默认编队：下面各场景没单独填编队时都用它' }),
      field('借好友助战', true, 'boolean', { description: '默认借不借好友助战' }),
      field('助战角色', '威玛西娜', 'text'),
      field('助战最低椎数', 6, 'integer', { minimum: 0, maximum: 6 }),
      field('找不到就借战力最高', true, 'boolean'),
      ...['推图', '竞技场', '体力本', '班组', '尘烟前哨战', '活动', '扩编实练'].map((sc) => field(`${sc}编队`, sc === '竞技场' ? '编队2' : '', 'text', { description: `${sc}用的编队，留空沿用默认编队` })),
      ...['推图', '尘烟前哨战'].map((sc) => field(`${sc}助战`, '沿用全局', 'select', { options: ['沿用全局', '开', '关'] })),
    ] },
    { name: '窗口', description: '游戏窗口与截图方式', fields: [field('窗口标题', '少女前线2：追放', 'text'), field('截图方式', 'BitBlt', 'select', { options: ['BitBlt', 'WGC', 'PrintWindow'] }), field('启动时置顶', false, 'boolean')] },
  ],
};

let logLines = [];
const log = (level, msg) => {
  const now = new Date();
  const ts = now.toISOString().replace('T', ' ').replace(/\.\d+Z$/, `,${String(now.getMilliseconds()).padStart(3, '0')}`);
  logLines.push(`${ts} ${level} TaskExecutor DailyTask:${msg}`);
  if (logLines.length > 500) logLines = logLines.slice(-500);
};
log('INFO', 'mock 后端启动');

const findTask = (name) => state.tasks.find((t) => t.name === decodeURIComponent(name));
const json = (res, code, data) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(data)); };
const readBody = (req) => new Promise((r) => { let b = ''; req.on('data', (c) => (b += c)); req.on('end', () => r(b ? JSON.parse(b) : {})); });

let runTimer = null;
function startRun(task) {
  state.status = { running: true, paused: false, starting: false, current_task: task.name };
  task.running = true;
  log('INFO', `开始 ${task.name}`);
  const steps = task.class_name === 'DailyTask' ? task.config.filter((f) => f.kind === 'boolean' && !f.sub_config && f.value).map((f) => f.key) : ['执行中'];
  let i = 0;
  runTimer = setInterval(() => {
    if (state.status.paused) return;
    if (i < steps.length) {
      task.info.current_task = steps[i];
      log('INFO', `执行 ${steps[i]}`);
      if (task.class_name === 'DailyTask' && i > 0) task.info['今日已完成(含之前几次)'] = [...new Set([...(task.info['今日已完成(含之前几次)'] || []), steps[i - 1]])];
      i++;
    } else {
      stopRun();
      log('INFO', `${task.name} 完成`);
    }
  }, 1500);
}
const queue = [];
function stopRun() {
  clearInterval(runTimer);
  runTimer = null;
  for (const t of state.tasks) { t.running = false; if (t.info) delete t.info.current_task; }
  state.status = { running: false, paused: false, starting: false, current_task: null };
  const next = queue.shift();
  if (next) { log('INFO', `排队的任务开始：${next.name}`); startRun(next); }
}
let workflowsFile = {};

http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  const p = url.pathname;
  if (p === '/api/status') return json(res, 200, state.status);
  if (p === '/api/v2/workflows') {
    if (req.method === 'PUT') { workflowsFile = await readBody(req); log('INFO', `保存流程 ${workflowsFile.workflows?.length ?? 0} 个`); return json(res, 200, { ok: true }); }
    return json(res, 200, workflowsFile);
  }
  if (p === '/api/ui/capture') return json(res, 200, { title: '少前2 自动化（mock）', event_session_key: 'mock' });
  if (p === '/api/tasks') return json(res, 200, state.tasks);
  if (p === '/api/settings') return json(res, 200, state.settings);
  if (p === '/api/logs') return json(res, 200, { text: logLines.join('\n'), line_count: logLines.length });
  if (p === '/api/tools/capture') return json(res, 200, { resource_url: 'https://placehold.co/1280x720/1a4a8e/ffffff.png?text=mock+capture' });
  if (p === '/api/executor/pause') { state.status.paused = true; log('WARNING', '已暂停'); return json(res, 200, {}); }
  if (p === '/api/executor/resume') { state.status.paused = false; return json(res, 200, {}); }
  if (p === '/api/executor/stop-task') { stopRun(); log('INFO', '用户停止'); return json(res, 200, {}); }
  let m;
  if ((m = p.match(/^\/api\/tasks\/([^/]+)\/(start|action|config|config\/reset)$/))) {
    const task = findTask(m[1]);
    if (!task) return json(res, 404, { detail: '任务不存在' });
    const body = await readBody(req);
    if (m[2] === 'start') { if (state.status.running) { queue.push(task); log('INFO', `queue task while another task is running ${task.name}`); return json(res, 200, {}); } startRun(task); return json(res, 200, {}); }
    if (m[2] === 'action') { if (body.action === 'enable') task.enabled = true; if (body.action === 'disable') task.enabled = false; return json(res, 200, {}); }
    if (m[2] === 'config/reset') { for (const f of task.config) f.value = f.default; return json(res, 200, {}); }
    const f = task.config.find((x) => x.key === body.key);
    if (!f) return json(res, 400, { detail: `没有配置项 ${body.key}` });
    f.value = body.value;
    log('INFO', `配置 ${body.key} = ${JSON.stringify(body.value)}`);
    return json(res, 200, task);
  }
  if ((m = p.match(/^\/api\/settings\/([^/]+)\/(config|reset)$/))) {
    const g = state.settings.find((x) => x.name === decodeURIComponent(m[1]));
    if (!g) return json(res, 404, { detail: '设置组不存在' });
    const body = await readBody(req);
    if (m[2] === 'reset') { for (const f of g.fields) f.value = f.default; return json(res, 200, {}); }
    const f = g.fields.find((x) => x.key === body.key);
    if (!f) return json(res, 400, { detail: `没有设置项 ${body.key}` });
    f.value = body.value;
    return json(res, 200, g);
  }
  json(res, 404, { detail: `mock 没有 ${p}` });
}).listen(8765, '127.0.0.1', () => console.log('mock ok-script api on http://127.0.0.1:8765'));
