/** ok-script Web 模式自带的 /api 接口的类型与封装。 */

export type FieldKind =
  | 'boolean'
  | 'integer'
  | 'number'
  | 'select'
  | 'list'
  | 'multi_selection'
  | 'multiline'
  | 'file'
  | 'text';

export interface ConfigField {
  key: string;
  value: unknown;
  default?: unknown;
  description?: string;
  kind: FieldKind | string;
  options?: unknown[] | null;
  minimum?: number | null;
  maximum?: number | null;
  sub_config?: boolean;
  allow_duplication?: boolean;
}

export interface TaskInfo {
  name: string;
  class_name: string;
  enabled: boolean;
  running: boolean;
  paused?: boolean;
  trigger?: boolean;
  description?: string;
  info?: Record<string, unknown>;
  config: ConfigField[];
}

export interface SettingsGroup {
  name: string;
  description?: string;
  fields: ConfigField[];
}

export interface ExecutorStatus {
  running?: boolean;
  paused?: boolean;
  starting?: boolean;
  current_task?: string | null;
  [k: string]: unknown;
}

/** 组件库里的一个「块」：可以加进任意流程 */
export interface CatalogComponent {
  id: string;
  label: string;
  task: string;
  /** 在任务配置里的开关键；null = 整个任务就是一块 */
  enable_key: string | null;
  keys: string[] | '*';
  /** 用到的阵容场景（全局「阵容与助战」里的 <场景>编队 / <场景>助战） */
  lineup_scopes?: string[];
  doc?: string;
}

export interface CatalogGroup {
  id: string;
  label: string;
  icon?: string;
  desc?: string;
  components: CatalogComponent[];
}

export interface CatalogGlobalSection {
  label: string;
  desc?: string;
  task: string;
  keys: string[];
}

export interface CatalogPreset {
  id: string;
  label: string;
  desc?: string;
  components: string[];
}

/** 第一次打开时自动建好的默认流程 */
export interface CatalogTemplate {
  id: string;
  label: string;
  icon?: string;
  desc?: string;
  components: string[];
  presets?: string[];
}

export interface Catalog {
  groups: CatalogGroup[];
  templates: CatalogTemplate[];
  presets: CatalogPreset[];
  global_sections: CatalogGlobalSection[];
}

// ---------- 用户自己拼的流程（页签），存在后端 configs/workflows.json ----------

export interface WorkflowItem {
  uid: string;
  component: string;
  enabled: boolean;
  /** 这一块在这个流程里的选项值（没写的键用任务默认值） */
  config: Record<string, unknown>;
  /** 这一块在这个流程里的阵容：<场景>编队 / <场景>助战（没写 = 沿用全局） */
  lineup: Record<string, string>;
}

export interface Workflow {
  id: string;
  label: string;
  icon?: string;
  desc?: string;
  presets?: string[];
  items: WorkflowItem[];
}

export interface WorkflowsFile {
  version: number;
  workflows: Workflow[];
}

export class ApiError extends Error {}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await fetch(path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = (await resp.json()) as { detail?: string };
      if (data.detail) detail = data.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail);
  }
  const text = await resp.text();
  return (text ? JSON.parse(text) : null) as T;
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
};

export const taskPath = (name: string) => `/api/tasks/${encodeURIComponent(name)}`;

export const endpoints = {
  catalog: () => api.get<Catalog>('/v2/catalog.json'),
  ui: () => api.get<{ title?: string; event_session_key?: string }>('/api/ui/capture'),
  tasks: () => api.get<TaskInfo[]>('/api/tasks'),
  status: () => api.get<ExecutorStatus>('/api/status'),
  settings: () => api.get<SettingsGroup[]>('/api/settings'),
  logs: (level: string, query: string) =>
    api.get<{ text: string; line_count?: number }>(
      `/api/logs?level=${encodeURIComponent(level)}&query=${encodeURIComponent(query)}`,
    ),
  setTaskConfig: (task: string, key: string, value: unknown) =>
    api.post<TaskInfo>(`${taskPath(task)}/config`, { key, value }),
  resetTaskConfig: (task: string) => api.post<unknown>(`${taskPath(task)}/config/reset`),
  startTask: (task: string) => api.post<unknown>(`${taskPath(task)}/start`),
  taskAction: (task: string, action: string) =>
    api.post<unknown>(`${taskPath(task)}/action`, { action }),
  setSetting: (group: string, key: string, value: unknown) =>
    api.post<SettingsGroup>(`/api/settings/${encodeURIComponent(group)}/config`, { key, value }),
  resetSetting: (group: string) =>
    api.post<unknown>(`/api/settings/${encodeURIComponent(group)}/reset`),
  pause: () => api.post<unknown>('/api/executor/pause'),
  resume: () => api.post<unknown>('/api/executor/resume'),
  stop: () => api.post<unknown>('/api/executor/stop-task'),
  capture: () => api.post<{ resource_url?: string }>('/api/tools/capture'),
  getWorkflows: () => api.get<Partial<WorkflowsFile> | null>('/api/v2/workflows'),
  saveWorkflows: (data: WorkflowsFile) => request<unknown>('PUT', '/api/v2/workflows', data),
};

export function eventsUrl(sessionKey: string): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}/api/events?session_key=${encodeURIComponent(sessionKey)}`;
}
