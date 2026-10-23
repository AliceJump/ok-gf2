import { create } from 'zustand';
import { toast } from 'sonner';
import {
  endpoints,
  eventsUrl,
  type Catalog,
  type CatalogComponent,
  type CatalogGroup,
  type CatalogPreset,
  type ConfigField,
  type ExecutorStatus,
  type SettingsGroup,
  type TaskInfo,
  type Workflow,
  type WorkflowItem,
  type WorkflowsFile,
} from './api';
import {
  applyTheme,
  loadThemeState,
  resolveThemeMode,
  saveThemeState,
  type ThemePreference,
} from './themes';

export type Page = 'main' | 'settings';

export interface LogLine {
  id: number;
  time: string;
  level: string;
  message: string;
}

export interface TaskProgress {
  done: string[];
  retry: string[];
  raw: Record<string, unknown>;
}

interface UiPrefs {
  workflow: string;
  expanded: string[];
  collapsedGroups: string[];
  rightPanelWidth: number;
  sidePanelExpanded: boolean;
  screenshotExpanded: boolean;
  statusExpanded: boolean;
  showPresetPanel: boolean;
  showAddPanel: boolean;
}

const PREFS_KEY = 'okgf2.ui';
const WORKFLOWS_VERSION = 1;
const NEW_WORKFLOW_ICON = '📋';

function loadPrefs(): UiPrefs {
  const base: UiPrefs = {
    workflow: 'daily',
    expanded: [],
    collapsedGroups: [],
    rightPanelWidth: 380,
    sidePanelExpanded: true,
    screenshotExpanded: true,
    statusExpanded: true,
    showPresetPanel: false,
    showAddPanel: false,
  };
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (raw) return { ...base, ...(JSON.parse(raw) as Partial<UiPrefs>) };
  } catch {
    /* ignore */
  }
  return base;
}

function savePrefs(p: UiPrefs): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(p));
  } catch {
    /* ignore */
  }
}

const LOG_NOISE = /ocr_zone|detected but no match|emit_draw|find_feature|wait_until timeout/;
const LOG_RE = /^(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d),\d+ (\w+) \S+ (?:\S+?:)?(.*)$/;

function parseLogs(text: string): LogLine[] {
  const out: LogLine[] = [];
  let id = 0;
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    const m = line.match(LOG_RE);
    if (m) {
      if (m[3] === 'DEBUG' || LOG_NOISE.test(m[4])) continue;
      out.push({ id: id++, time: m[2], level: m[3], message: m[4] });
    } else if (out.length) {
      out[out.length - 1].message += `\n${line}`;
    } else {
      out.push({ id: id++, time: '', level: 'INFO', message: line });
    }
  }
  return out.slice(-1500);
}

let uidCounter = 0;
export function newUid(prefix = 'i'): string {
  uidCounter += 1;
  return `${prefix}_${Date.now().toString(36)}${uidCounter.toString(36)}`;
}

interface State {
  ready: boolean;
  connectionError: string | null;
  title: string;
  catalog: Catalog | null;
  tasks: TaskInfo[];
  settings: SettingsGroup[];
  status: ExecutorStatus;
  logs: LogLine[];
  logLevel: string;
  logQuery: string;
  page: Page;
  prefs: UiPrefs;
  themePreference: ThemePreference;
  accent: string;
  screenshotUrl: string | null;
  screenshotError: string | null;
  streaming: boolean;
  busy: boolean;
  /** 用户自己拼的流程（页签） */
  workflows: Workflow[];
  /** 最近一次从界面启动的流程，顶栏页签的呼吸点用 */
  runningWorkflowId: string | null;
  /** 刚加进流程的块，用来播放入场动画 */
  justAdded: string | null;

  init: () => Promise<void>;
  refreshAll: () => Promise<void>;
  refreshTasks: () => Promise<void>;
  refreshStatus: () => Promise<void>;
  refreshSettings: () => Promise<void>;
  refreshLogs: () => Promise<void>;
  setLogFilter: (level: string, query: string) => void;
  clearLogs: () => void;

  setPage: (p: Page) => void;
  setPrefs: (patch: Partial<UiPrefs>) => void;
  toggleExpanded: (id: string) => void;
  setAllExpanded: (expanded: boolean) => void;
  toggleGroupCollapsed: (id: string) => void;
  setThemePreference: (p: ThemePreference) => void;
  setAccent: (a: string) => void;

  // 流程（页签）
  setWorkflow: (id: string) => void;
  addWorkflow: (label?: string, fromTemplate?: string) => string;
  duplicateWorkflow: (id: string) => string;
  renameWorkflow: (id: string, label: string) => void;
  setWorkflowIcon: (id: string, icon: string) => void;
  moveWorkflow: (id: string, delta: number) => void;
  removeWorkflow: (id: string) => void;
  // 流程里的块
  addItem: (componentId: string) => void;
  removeItem: (uid: string) => void;
  setItemEnabled: (uid: string, enabled: boolean) => void;
  setItemConfig: (uid: string, key: string, value: unknown) => void;
  setItemLineup: (uid: string, changes: [string, string | null][]) => void;
  resetItem: (uid: string) => void;
  setAllEnabled: (enabled: boolean) => void;
  applyPreset: (presetId: string) => void;
  // 运行
  startWorkflow: () => Promise<void>;
  runItem: (uid: string) => Promise<void>;
  stop: () => Promise<void>;
  togglePause: () => Promise<void>;

  // 后端直改（设置页、触发任务）
  setTaskConfig: (taskName: string, key: string, value: unknown) => Promise<void>;
  resetTaskConfig: (taskName: string) => Promise<void>;
  setSetting: (group: string, key: string, value: unknown) => Promise<void>;
  setSettings: (group: string, changes: [string, unknown][]) => Promise<void>;
  resetSetting: (group: string) => Promise<void>;
  taskAction: (taskName: string, action: string) => Promise<void>;
  captureOnce: () => Promise<void>;
  setStreaming: (on: boolean) => void;
}

let eventKey: string | null = null;
let refreshTimer: number | null = null;
let streamTimer: number | null = null;
let saveTimer: number | null = null;

function connectEvents(get: () => State) {
  if (!eventKey) return;
  try {
    const ws = new WebSocket(eventsUrl(eventKey));
    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data as string) as { event?: string };
        if (
          data.event &&
          ['task', 'task_list_updated', 'executor_paused', 'starting_emulator'].includes(data.event)
        ) {
          if (refreshTimer) window.clearTimeout(refreshTimer);
          refreshTimer = window.setTimeout(() => {
            get().refreshAll().catch(() => {});
          }, 300);
        }
      } catch {
        /* ignore */
      }
    };
    ws.onclose = () => {
      window.setTimeout(() => connectEvents(get), 3000);
    };
  } catch {
    /* ignore */
  }
}

/** 从目录模板生成默认流程（第一次打开、或 workflows.json 为空时） */
/**
 * 块加进流程时把后端当时的值复制进来（开关 + 选项），之后这份值只属于这个流程。
 * 不能用代码默认值：用户在后端关掉的东西（如商店心愿单购买）会被默认值悄悄打开（实录 2026-10-20）。
 */
function snapshotItem(item: WorkflowItem, catalog: Catalog, tasks: TaskInfo[]): WorkflowItem {
  const comp = componentById(catalog, tasks, item.component);
  const task = comp ? taskByClass({ tasks }, comp.task) : undefined;
  if (!comp || !task) return item;
  let config = item.config;
  for (const key of entryOptionKeys(comp, task)) {
    if (key in config) continue;
    const f = fieldOf(task, key);
    if (!f) continue;
    if (config === item.config) config = { ...config };
    config[key] = f.value;
  }
  return config === item.config ? item : { ...item, config };
}

function newItem(componentId: string, catalog: Catalog, tasks: TaskInfo[]): WorkflowItem {
  const comp = componentById(catalog, tasks, componentId);
  const task = comp ? taskByClass({ tasks }, comp.task) : undefined;
  const enableField = comp?.enable_key && task ? fieldOf(task, comp.enable_key) : undefined;
  const enabled = enableField ? !!enableField.value : true;
  return snapshotItem({ uid: newUid(), component: componentId, enabled, config: {}, lineup: {} }, catalog, tasks);
}

function snapshotWorkflows(list: Workflow[], catalog: Catalog, tasks: TaskInfo[]): Workflow[] {
  let changed = false;
  const out = list.map((wf) => {
    const items = wf.items.map((i) => snapshotItem(i, catalog, tasks));
    if (items.some((it, idx) => it !== wf.items[idx])) {
      changed = true;
      return { ...wf, items };
    }
    return wf;
  });
  return changed ? out : list;
}

function workflowsFromTemplates(catalog: Catalog, tasks: TaskInfo[]): Workflow[] {
  return catalog.templates.map((t) => ({
    id: t.id,
    label: t.label,
    icon: t.icon,
    desc: t.desc,
    presets: t.presets,
    items: t.components.map((c) => newItem(c, catalog, tasks)),
  }));
}

function normalizeWorkflows(raw: Partial<WorkflowsFile> | null | undefined): Workflow[] {
  const list = Array.isArray(raw?.workflows) ? raw!.workflows! : [];
  return list
    .filter((w) => w && typeof w.id === 'string' && typeof w.label === 'string')
    .map((w) => ({
      id: w.id,
      label: w.label,
      icon: w.icon,
      desc: w.desc,
      presets: Array.isArray(w.presets) ? w.presets : undefined,
      items: (Array.isArray(w.items) ? w.items : [])
        .filter((i) => i && typeof i.component === 'string')
        .map((i) => ({
          uid: typeof i.uid === 'string' ? i.uid : newUid(),
          component: i.component,
          enabled: i.enabled !== false,
          config: i.config && typeof i.config === 'object' ? i.config : {},
          lineup: i.lineup && typeof i.lineup === 'object' ? i.lineup : {},
        })),
    }));
}

export const useStore = create<State>((set, get) => {
  const theme = loadThemeState();
  applyTheme(resolveThemeMode(theme.preference), theme.accent);
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    const s = get();
    if (s.themePreference === 'system') applyTheme(resolveThemeMode('system'), s.accent);
  });

  /** 改流程后写回后端（合并 500ms 内的多次改动） */
  const updateWorkflows = (fn: (list: Workflow[]) => Workflow[]) => {
    const workflows = fn(get().workflows);
    set({ workflows });
    if (saveTimer) window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => {
      endpoints
        .saveWorkflows({ version: WORKFLOWS_VERSION, workflows: get().workflows })
        .catch((e: Error) => toast.error(`流程没保存上：${e.message}`));
    }, 500);
  };

  const updateCurrentItems = (fn: (items: WorkflowItem[]) => WorkflowItem[]) => {
    const wf = currentWorkflow(get());
    if (!wf) return;
    updateWorkflows((list) => list.map((w) => (w.id === wf.id ? { ...w, items: fn(w.items) } : w)));
  };

  /** 把一组块的开关 / 选项 / 阵容写进后端，返回要依次启动的任务名 */
  const applyItems = async (items: WorkflowItem[]): Promise<string[]> => {
    const s = get();
    const catalog = s.catalog!;
    const comps = allComponents(catalog, s.tasks);
    const picked = items
      .map((i) => ({ item: i, comp: comps.find((c) => c.id === i.component) }))
      .filter((x): x is { item: WorkflowItem; comp: CatalogComponent } => !!x.comp);
    const taskOrder: string[] = [];
    for (const { comp } of picked) {
      const t = s.tasks.find((x) => x.class_name === comp.task);
      if (!t) {
        toast.warning(`「${comp.label}」的任务 ${comp.task} 没有注册，跳过`);
        continue;
      }
      if (t.trigger) continue;
      if (!taskOrder.includes(comp.task)) taskOrder.push(comp.task);
    }
    const names: string[] = [];
    for (const cls of taskOrder) {
      let task = s.tasks.find((x) => x.class_name === cls)!;
      const mine = picked.filter((x) => x.comp.task === cls);
      const desired = new Map<string, unknown>();
      // 这个任务的所有开关键：在流程里且勾了的开，其它一律关 —— 这样每个流程的设置互不干扰
      for (const c of comps) if (c.task === cls && c.enable_key) desired.set(c.enable_key, mine.some((x) => x.comp.id === c.id));
      for (const { item, comp } of mine) {
        for (const key of entryOptionKeys(comp, task)) {
          const f = fieldOf(task, key);
          if (!f) continue;
          // 只写这个流程里记下的值；没记（理论上加块时已经复制过）就不动后端
          if (key in item.config) desired.set(key, item.config[key]);
        }
      }
      for (const [key, value] of desired) {
        const f = fieldOf(task, key);
        if (!f || JSON.stringify(f.value) === JSON.stringify(value)) continue;
        task = await endpoints.setTaskConfig(task.name, key, value);
      }
      names.push(task.name);
    }
    // 阵容：流程里每块自己的编队/助战写进全局「阵容与助战」（没单独设的写成沿用全局）
    const lineupChanges: [string, unknown][] = [];
    const scopesDone = new Set<string>();
    for (const { item, comp } of picked) {
      for (const scope of comp.lineup_scopes ?? []) {
        if (scopesDone.has(scope)) continue;
        scopesDone.add(scope);
        const presetKey = `${scope}编队`;
        const supportKey = `${scope}助战`;
        if (lineupField(s.settings, presetKey)) {
          const v = item.lineup[presetKey] ?? '';
          if (String(lineupField(s.settings, presetKey)!.value ?? '') !== v) lineupChanges.push([presetKey, v]);
        }
        if (lineupField(s.settings, supportKey)) {
          const v = item.lineup[supportKey] ?? SUPPORT_INHERIT;
          if (String(lineupField(s.settings, supportKey)!.value || SUPPORT_INHERIT) !== v) lineupChanges.push([supportKey, v]);
        }
      }
    }
    if (lineupChanges.length) await get().setSettings(LINEUP_GROUP, lineupChanges);
    return names;
  };

  return {
    ready: false,
    connectionError: null,
    title: '少前2 自动化',
    catalog: null,
    tasks: [],
    settings: [],
    status: {},
    logs: [],
    logLevel: 'ALL',
    logQuery: '',
    page: 'main',
    prefs: loadPrefs(),
    themePreference: theme.preference,
    accent: theme.accent,
    screenshotUrl: null,
    screenshotError: null,
    streaming: false,
    busy: false,
    workflows: [],
    runningWorkflowId: null,
    justAdded: null,

    async init() {
      try {
        const [catalog, ui] = await Promise.all([endpoints.catalog(), endpoints.ui()]);
        eventKey = ui.event_session_key ?? null;
        set({ catalog, title: ui.title || '少前2 自动化', connectionError: null });
        document.title = ui.title || '少前2 自动化';
        await get().refreshAll();
        const loaded = normalizeWorkflows(await endpoints.getWorkflows().catch(() => null));
        let workflows = loaded;
        if (!workflows.length) {
          workflows = workflowsFromTemplates(catalog, get().tasks);
        } else {
          // 旧文件里没记值的键，补上后端当前值
          workflows = snapshotWorkflows(workflows, catalog, get().tasks);
        }
        if (workflows !== loaded) endpoints.saveWorkflows({ version: WORKFLOWS_VERSION, workflows }).catch(() => {});
        set({ workflows, ready: true });
        connectEvents(get);
        get().refreshLogs().catch(() => {});
        window.setInterval(() => {
          get().refreshLogs().catch(() => {});
          get().refreshStatus().catch(() => {});
          // 运行中时任务的 info（当前子任务/今日已完成）会变，没有事件推送也要跟上
          if (get().status.running) get().refreshTasks().catch(() => {});
        }, 2000);
      } catch (err) {
        set({ connectionError: (err as Error).message });
        window.setTimeout(() => get().init(), 3000);
      }
    },

    async refreshAll() {
      await Promise.all([get().refreshTasks(), get().refreshStatus(), get().refreshSettings()]);
    },
    async refreshTasks() {
      const tasks = await endpoints.tasks();
      set({ tasks, connectionError: null });
    },
    async refreshStatus() {
      const status = await endpoints.status();
      const idle = !status.running || !status.current_task;
      set({ status, connectionError: null, ...(idle && !status.starting ? { runningWorkflowId: null } : {}) });
    },
    async refreshSettings() {
      const settings = await endpoints.settings();
      set({ settings });
    },
    async refreshLogs() {
      const { logLevel, logQuery } = get();
      const data = await endpoints.logs(logLevel, logQuery);
      set({ logs: parseLogs(data.text || '') });
    },
    setLogFilter(level, query) {
      set({ logLevel: level, logQuery: query });
      get().refreshLogs().catch(() => {});
    },
    clearLogs() {
      set({ logs: [] });
    },

    setPage(page) {
      set({ page });
      if (page === 'settings') get().refreshSettings().catch((e: Error) => toast.error(e.message));
    },
    setPrefs(patch) {
      const prefs = { ...get().prefs, ...patch };
      savePrefs(prefs);
      set({ prefs });
    },
    toggleExpanded(id) {
      const cur = new Set(get().prefs.expanded);
      if (cur.has(id)) cur.delete(id);
      else cur.add(id);
      get().setPrefs({ expanded: [...cur] });
    },
    setAllExpanded(expanded) {
      const wf = currentWorkflow(get());
      if (!wf) return;
      const mine = new Set(wf.items.map((i) => i.uid));
      const others = get().prefs.expanded.filter((id) => !mine.has(id));
      get().setPrefs({ expanded: expanded ? [...others, ...mine] : others });
    },
    toggleGroupCollapsed(id) {
      const cur = new Set(get().prefs.collapsedGroups);
      if (cur.has(id)) cur.delete(id);
      else cur.add(id);
      get().setPrefs({ collapsedGroups: [...cur] });
    },
    setThemePreference(preference) {
      const accent = get().accent;
      saveThemeState({ preference, accent });
      applyTheme(resolveThemeMode(preference), accent);
      set({ themePreference: preference });
    },
    setAccent(accent) {
      const preference = get().themePreference;
      saveThemeState({ preference, accent });
      applyTheme(resolveThemeMode(preference), accent);
      set({ accent });
    },

    // ---------- 流程（页签） ----------
    setWorkflow(id) {
      get().setPrefs({ workflow: id, showAddPanel: false, showPresetPanel: false });
    },
    addWorkflow(label, fromTemplate) {
      const id = newUid('wf');
      const catalog = get().catalog;
      const tpl = fromTemplate && catalog ? catalog.templates.find((t) => t.id === fromTemplate) : undefined;
      const wf: Workflow = tpl
        ? { ...workflowsFromTemplates({ ...catalog!, templates: [tpl] }, get().tasks)[0], id, label: label || tpl.label }
        : { id, label: label || '新流程', icon: NEW_WORKFLOW_ICON, items: [] };
      updateWorkflows((list) => [...list, wf]);
      get().setWorkflow(id);
      return id;
    },
    duplicateWorkflow(id) {
      const src = get().workflows.find((w) => w.id === id);
      if (!src) return id;
      const nid = newUid('wf');
      const copy: Workflow = {
        ...src,
        id: nid,
        label: `${src.label} 副本`,
        items: src.items.map((i) => ({ ...i, uid: newUid(), config: { ...i.config }, lineup: { ...i.lineup } })),
      };
      updateWorkflows((list) => {
        const idx = list.findIndex((w) => w.id === id);
        return [...list.slice(0, idx + 1), copy, ...list.slice(idx + 1)];
      });
      get().setWorkflow(nid);
      return nid;
    },
    renameWorkflow(id, label) {
      const name = label.trim();
      if (!name) return;
      updateWorkflows((list) => list.map((w) => (w.id === id ? { ...w, label: name } : w)));
    },
    setWorkflowIcon(id, icon) {
      updateWorkflows((list) => list.map((w) => (w.id === id ? { ...w, icon } : w)));
    },
    moveWorkflow(id, delta) {
      updateWorkflows((list) => {
        const idx = list.findIndex((w) => w.id === id);
        const to = idx + delta;
        if (idx < 0 || to < 0 || to >= list.length) return list;
        const next = [...list];
        const [w] = next.splice(idx, 1);
        next.splice(to, 0, w);
        return next;
      });
    },
    removeWorkflow(id) {
      const list = get().workflows;
      if (list.length <= 1) {
        toast.error('至少要留一个流程');
        return;
      }
      const idx = list.findIndex((w) => w.id === id);
      updateWorkflows((l) => l.filter((w) => w.id !== id));
      if (get().prefs.workflow === id) {
        const next = get().workflows[Math.max(0, idx - 1)];
        if (next) get().setWorkflow(next.id);
      }
    },

    // ---------- 流程里的块 ----------
    addItem(componentId) {
      const wf = currentWorkflow(get());
      if (!wf) return;
      if (wf.items.some((i) => i.component === componentId)) {
        toast.info('这一块已经在流程里了（同一块在一个流程里只能有一份）');
        return;
      }
      const catalog = get().catalog;
      if (!catalog) return;
      const item = newItem(componentId, catalog, get().tasks);
      updateCurrentItems((items) => [...items, item]);
      set({ justAdded: item.uid });
      window.setTimeout(() => get().justAdded === item.uid && set({ justAdded: null }), 400);
    },
    removeItem(uid) {
      updateCurrentItems((items) => items.filter((i) => i.uid !== uid));
      get().setPrefs({ expanded: get().prefs.expanded.filter((id) => id !== uid) });
    },
    setItemEnabled(uid, enabled) {
      updateCurrentItems((items) => items.map((i) => (i.uid === uid ? { ...i, enabled } : i)));
    },
    setItemConfig(uid, key, value) {
      updateCurrentItems((items) => items.map((i) => (i.uid === uid ? { ...i, config: { ...i.config, [key]: value } } : i)));
    },
    setItemLineup(uid, changes) {
      updateCurrentItems((items) =>
        items.map((i) => {
          if (i.uid !== uid) return i;
          const lineup = { ...i.lineup };
          for (const [k, v] of changes) {
            if (v === null || v === '') delete lineup[k];
            else lineup[k] = v;
          }
          return { ...i, lineup };
        }),
      );
    },
    resetItem(uid) {
      const catalog = get().catalog;
      const tasks = get().tasks;
      updateCurrentItems((items) =>
        items.map((i) => {
          if (i.uid !== uid || !catalog) return i;
          const comp = componentById(catalog, tasks, i.component);
          const task = comp ? taskByClass({ tasks }, comp.task) : undefined;
          const config: Record<string, unknown> = {};
          if (comp && task)
            for (const key of entryOptionKeys(comp, task)) {
              const f = fieldOf(task, key);
              if (f) config[key] = f.default !== undefined ? f.default : f.value;
            }
          return { ...i, config, lineup: {} };
        }),
      );
      toast.success('已恢复这一块的默认值');
    },
    setAllEnabled(enabled) {
      updateCurrentItems((items) => items.map((i) => ({ ...i, enabled })));
    },
    applyPreset(presetId) {
      const catalog = get().catalog;
      const preset = catalog?.presets.find((p) => p.id === presetId);
      if (!catalog || !preset) return;
      const want = new Set(preset.components);
      let added = 0;
      updateCurrentItems((items) => {
        const next = items.map((i) => ({ ...i, enabled: want.has(i.component) }));
        for (const c of preset.components)
          if (!next.some((i) => i.component === c)) {
            next.push({ uid: newUid(), component: c, enabled: true, config: {}, lineup: {} });
            added++;
          }
        return next;
      });
      toast.success(`已应用「${preset.label}」${added ? `，补进了 ${added} 块` : ''}`);
    },

    // ---------- 运行 ----------
    async startWorkflow() {
      const wf = currentWorkflow(get());
      if (!wf) return;
      const items = wf.items.filter((i) => i.enabled);
      if (!items.length) {
        toast.error('这个流程里没有勾选任何块');
        return;
      }
      set({ busy: true });
      try {
        const names = await applyItems(items);
        if (!names.length) {
          toast.error('没有可以启动的任务');
          return;
        }
        for (const name of names) await endpoints.startTask(name);
        set({ runningWorkflowId: wf.id });
        toast.success(names.length > 1 ? `已启动「${wf.label}」：${names.join(' → ')}` : `已启动「${wf.label}」`);
        await get().refreshAll();
      } catch (err) {
        toast.error(`启动失败：${(err as Error).message}`);
      } finally {
        set({ busy: false });
      }
    },
    async runItem(uid) {
      const wf = currentWorkflow(get());
      const item = wf?.items.find((i) => i.uid === uid);
      if (!wf || !item) return;
      set({ busy: true });
      try {
        const names = await applyItems([item]);
        for (const name of names) await endpoints.startTask(name);
        set({ runningWorkflowId: wf.id });
        if (names.length) toast.success(`已启动「${names[0]}」`);
        await get().refreshAll();
      } catch (err) {
        toast.error(`启动失败：${(err as Error).message}`);
      } finally {
        set({ busy: false });
      }
    },
    async stop() {
      set({ busy: true });
      try {
        await endpoints.stop();
        toast.info('已发送停止');
        await get().refreshAll();
      } catch (err) {
        toast.error(`停止失败：${(err as Error).message}`);
      } finally {
        set({ busy: false });
      }
    },
    async togglePause() {
      try {
        if (get().status.paused) await endpoints.resume();
        else await endpoints.pause();
        await get().refreshAll();
      } catch (err) {
        toast.error(`操作失败：${(err as Error).message}`);
      }
    },

    // ---------- 后端直改 ----------
    async setTaskConfig(taskName, key, value) {
      try {
        const updated = await endpoints.setTaskConfig(taskName, key, value);
        set({ tasks: get().tasks.map((t) => (t.class_name === updated.class_name ? updated : t)) });
      } catch (err) {
        toast.error(`保存失败：${(err as Error).message}`);
        throw err;
      }
    },
    async resetTaskConfig(taskName) {
      try {
        await endpoints.resetTaskConfig(taskName);
        await get().refreshTasks();
        toast.success('已恢复默认');
      } catch (err) {
        toast.error(`失败：${(err as Error).message}`);
      }
    },
    async setSetting(group, key, value) {
      try {
        const updated = await endpoints.setSetting(group, key, value);
        set({ settings: get().settings.map((g) => (g.name === updated.name ? updated : g)) });
      } catch (err) {
        toast.error(`保存失败：${(err as Error).message}`);
      }
    },
    async setSettings(group, changes) {
      try {
        let updated: SettingsGroup | null = null;
        for (const [key, value] of changes) updated = await endpoints.setSetting(group, key, value);
        if (updated) {
          const u = updated;
          set({ settings: get().settings.map((g) => (g.name === u.name ? u : g)) });
        }
      } catch (err) {
        toast.error(`保存失败：${(err as Error).message}`);
        throw err;
      }
    },
    async resetSetting(group) {
      try {
        await endpoints.resetSetting(group);
        await get().refreshSettings();
        toast.success('已恢复默认');
      } catch (err) {
        toast.error(`失败：${(err as Error).message}`);
      }
    },
    async taskAction(taskName, action) {
      try {
        await endpoints.taskAction(taskName, action);
        await get().refreshAll();
      } catch (err) {
        toast.error(`失败：${(err as Error).message}`);
      }
    },
    async captureOnce() {
      try {
        const r = await endpoints.capture();
        set({
          screenshotUrl: r.resource_url || `/api/capture/image?t=${Date.now()}`,
          screenshotError: null,
        });
      } catch (err) {
        set({ screenshotError: (err as Error).message });
      }
    },
    setStreaming(on) {
      if (streamTimer) {
        window.clearInterval(streamTimer);
        streamTimer = null;
      }
      set({ streaming: on });
      if (on) {
        get().captureOnce().catch(() => {});
        streamTimer = window.setInterval(() => get().captureOnce().catch(() => {}), 3000);
      }
    },
  };
});

// ---------- 派生数据 ----------

export function taskByClass(s: Pick<State, 'tasks'>, cls: string): TaskInfo | undefined {
  return s.tasks.find((t) => t.class_name === cls);
}

export function fieldOf(task: TaskInfo | undefined, key: string): ConfigField | undefined {
  return task?.config.find((f) => f.key === key);
}

export function currentWorkflow(s: Pick<State, 'workflows' | 'prefs'>): Workflow | undefined {
  return s.workflows.find((w) => w.id === s.prefs.workflow) ?? s.workflows[0];
}

const UNLISTED_GROUP_ID = '_unlisted';

/** 组件库分组 + 兜底：后端注册了但目录里没列的任务，自动成为「其它任务」组里的整任务块 */
export function allGroups(catalog: Catalog, tasks: TaskInfo[]): CatalogGroup[] {
  const listed = new Set(catalog.groups.flatMap((g) => g.components.map((c) => c.task)));
  const unlisted = tasks.filter((t) => !listed.has(t.class_name));
  if (!unlisted.length) return catalog.groups;
  return [
    ...catalog.groups,
    {
      id: UNLISTED_GROUP_ID,
      label: '其它任务',
      icon: '📦',
      desc: '后端注册了、但目录里还没列出的任务。',
      components: unlisted.map((t) => ({ id: `task:${t.class_name}`, label: t.name, task: t.class_name, enable_key: null, keys: '*' as const })),
    },
  ];
}

export function allComponents(catalog: Catalog, tasks: TaskInfo[]): CatalogComponent[] {
  return allGroups(catalog, tasks).flatMap((g) => g.components);
}

export function componentById(catalog: Catalog, tasks: TaskInfo[], id: string): CatalogComponent | undefined {
  return allComponents(catalog, tasks).find((c) => c.id === id);
}

export function groupOfComponent(catalog: Catalog, tasks: TaskInfo[], id: string): CatalogGroup | undefined {
  return allGroups(catalog, tasks).find((g) => g.components.some((c) => c.id === id));
}

/** 流程里的块按组件库的分组排好：[分组, 该组里的块（按目录顺序）] */
export function groupedItems(
  wf: Workflow,
  catalog: Catalog,
  tasks: TaskInfo[],
): { group: CatalogGroup; items: { item: WorkflowItem; component: CatalogComponent }[] }[] {
  const out: { group: CatalogGroup; items: { item: WorkflowItem; component: CatalogComponent }[] }[] = [];
  for (const group of allGroups(catalog, tasks)) {
    const items: { item: WorkflowItem; component: CatalogComponent }[] = [];
    for (const component of group.components) {
      const item = wf.items.find((i) => i.component === component.id);
      if (item) items.push({ item, component });
    }
    if (items.length) out.push({ group, items });
  }
  return out;
}

/** 流程里引用了、但组件库里已经没有的块（目录改名后可能出现） */
export function orphanItems(wf: Workflow, catalog: Catalog, tasks: TaskInfo[]): WorkflowItem[] {
  const ids = new Set(allComponents(catalog, tasks).map((c) => c.id));
  return wf.items.filter((i) => !ids.has(i.component));
}

export function presetsOf(wf: Workflow | undefined, catalog: Catalog | null): CatalogPreset[] {
  if (!wf || !catalog || !wf.presets?.length) return [];
  return wf.presets.map((id) => catalog.presets.find((p) => p.id === id)).filter((p): p is CatalogPreset => !!p);
}

/** 哪个流程在跑：优先记住的那个，否则按正在跑的任务反查第一个包含它的流程 */
export function runningWorkflow(s: Pick<State, 'workflows' | 'runningWorkflowId' | 'status' | 'tasks' | 'catalog'>): Workflow | undefined {
  const running = !!s.status.running && !!s.status.current_task;
  if (!running) return undefined;
  const byId = s.workflows.find((w) => w.id === s.runningWorkflowId);
  if (byId) return byId;
  const cls = s.tasks.find((t) => t.name === s.status.current_task)?.class_name;
  if (!cls || !s.catalog) return undefined;
  const comps = allComponents(s.catalog, s.tasks);
  return s.workflows.find((w) => w.items.some((i) => i.enabled && comps.find((c) => c.id === i.component)?.task === cls));
}

/** 任务 info 里的「今日已完成 / 今日待重试」（一键日常会写，其它任务一般为空） */
export function taskProgress(task: TaskInfo | undefined): TaskProgress {
  const info = (task?.info ?? {}) as Record<string, unknown>;
  const findList = (needle: string): string[] => {
    const k = Object.keys(info).find((x) => x.includes(needle));
    const v = k ? info[k] : undefined;
    return Array.isArray(v) ? (v as string[]) : [];
  };
  return { done: findList('今日已完成'), retry: findList('今日待重试'), raw: info };
}

/** 块的选项键列表（enable_key 之外的） */
export function entryOptionKeys(component: CatalogComponent, task: TaskInfo | undefined): string[] {
  if (!task) return [];
  if (component.keys === '*') return task.config.map((f) => f.key).filter((k) => k !== component.enable_key);
  return component.keys;
}

/** 把块在这个流程里的值套到任务字段上（没记的键显示后端当前值），给选项编辑器用 */
export function itemFields(item: WorkflowItem, task: TaskInfo): ConfigField[] {
  return task.config.map((f) => ({
    ...f,
    value: f.key in item.config ? item.config[f.key] : f.value,
  }));
}

/** 这一块在这个流程里有多少项和代码默认值不一样（选项 + 阵容） */
export function itemChangedCount(item: WorkflowItem, component: CatalogComponent, task: TaskInfo | undefined): number {
  let n = Object.keys(item.lineup).length;
  if (!task) return n;
  for (const key of entryOptionKeys(component, task)) {
    if (!(key in item.config)) continue;
    const f = fieldOf(task, key);
    const def = f ? (f.default !== undefined ? f.default : f.value) : undefined;
    if (JSON.stringify(item.config[key]) !== JSON.stringify(def)) n++;
  }
  return n;
}

// ---------- 阵容场景（全局「阵容与助战」里的 <场景>编队 / <场景>助战） ----------
// 优先级：内置默认 → 全局值 → 流程里这一块单独设置；没单独设就继承

export const LINEUP_GROUP = '阵容与助战';
export const LINEUP_PRESET = '编队名';
export const LINEUP_SUPPORT = '借好友助战';
export const SUPPORT_INHERIT = '沿用全局';

export interface ScopeState {
  scope: string;
  /** 这一块单独设的编队（'' = 沿用） */
  preset: string;
  globalPreset: string;
  effectivePreset: string;
  /** null = 这个场景不支持借助战 */
  support: string | null;
  globalSupport: boolean;
  effectiveSupport: boolean | null;
  overridden: boolean;
}

export function lineupGroup(settings: SettingsGroup[]): SettingsGroup | undefined {
  return settings.find((g) => g.name === LINEUP_GROUP);
}

export function lineupField(settings: SettingsGroup[], key: string): ConfigField | undefined {
  return lineupGroup(settings)?.fields.find((f) => f.key === key);
}

/** 有「X编队」键的 X 就是一个场景（「编队名」不以「编队」结尾，不会混进来） */
export function lineupScopes(settings: SettingsGroup[]): string[] {
  const g = lineupGroup(settings);
  return g ? g.fields.filter((f) => f.key.endsWith('编队')).map((f) => f.key.slice(0, -2)) : [];
}

export function isScopeKey(settings: SettingsGroup[], key: string): boolean {
  return lineupScopes(settings).some((s) => key === `${s}编队` || key === `${s}助战`);
}

/** 某个场景在这一块里的生效情况；lineup 不传就是看全局本身 */
export function scopeState(settings: SettingsGroup[], scope: string, lineup: Record<string, string> = {}): ScopeState | null {
  const presetField = lineupField(settings, `${scope}编队`);
  if (!presetField) return null;
  const preset = String(lineup[`${scope}编队`] ?? '').trim();
  const globalPreset = String(lineupField(settings, LINEUP_PRESET)?.value ?? '').trim();
  const supportField = lineupField(settings, `${scope}助战`);
  const support = supportField ? String(lineup[`${scope}助战`] || SUPPORT_INHERIT) : null;
  const globalSupport = lineupField(settings, LINEUP_SUPPORT)?.value !== false;
  return {
    scope,
    preset,
    globalPreset,
    effectivePreset: preset || globalPreset || '不切编队',
    support,
    globalSupport,
    effectiveSupport: support === null ? null : support === SUPPORT_INHERIT ? globalSupport : support === '开',
    overridden: !!preset || (support !== null && support !== SUPPORT_INHERIT),
  };
}
