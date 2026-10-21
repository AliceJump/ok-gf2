/** 右侧「运行状态」卡片（对应 MXU 的连接面板位置）。 */
import { useMemo } from 'react';
import clsx from 'clsx';
import { Activity, ChevronDown } from 'lucide-react';
import { taskProgress, useStore } from '@/store';

export function StatusIndicator() {
  const status = useStore((s) => s.status);
  const error = useStore((s) => s.connectionError);
  const running = !!status.running && !!status.current_task;
  const text = error
    ? '连不上后端'
    : status.paused
      ? '已暂停'
      : running
        ? `运行中：${status.current_task}`
        : status.starting
          ? '正在启动…'
          : '空闲';
  return (
    <span className="flex items-center gap-1.5 text-xs text-text-secondary">
      <span
        className={clsx(
          'w-2 h-2 rounded-full',
          error ? 'bg-error' : status.paused ? 'bg-warning' : running ? 'bg-accent task-running-indicator' : 'bg-text-muted',
        )}
      />
      <span className="truncate max-w-[180px]">{text}</span>
    </span>
  );
}

export function StatusPanel() {
  const expanded = useStore((s) => s.prefs.statusExpanded);
  const setPrefs = useStore((s) => s.setPrefs);
  const status = useStore((s) => s.status);
  const tasks = useStore((s) => s.tasks);
  // 正在跑的任务的 info；空闲时看一键日常的（今日已完成 / 待重试）
  const di = useMemo(() => {
    const cur = tasks.find((t) => t.name === status.current_task);
    const withInfo = tasks.find((t) => t.info && Object.keys(t.info).length > 0);
    return taskProgress(cur && cur.info && Object.keys(cur.info).length ? cur : withInfo);
  }, [tasks, status.current_task]);

  const skip = new Set(['今日已完成(含之前几次)', '今日待重试', 'current_task']);
  const rows: [string, string][] = [
    ['执行器', status.paused ? '暂停' : status.running ? '运行' : '停止'],
    ['当前任务', String(status.current_task || '无')],
  ];
  for (const [k, v] of Object.entries(di.raw)) {
    if (skip.has(k)) continue;
    rows.push([k, Array.isArray(v) ? v.join('、') : String(v)]);
  }
  if (di.done.length) rows.push(['今日已完成', di.done.join('、')]);
  if (di.retry.length) rows.push(['今日待重试', di.retry.join('、')]);

  return (
    <div className="bg-bg-secondary rounded-lg ring-1 ring-inset ring-border overflow-hidden shrink-0">
      <button
        type="button"
        onClick={() => setPrefs({ statusExpanded: !expanded })}
        className={clsx(
          'w-full flex items-center justify-between px-3 py-2 hover:bg-bg-hover focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/50 outline-none',
          expanded ? 'rounded-t-lg' : 'rounded-lg',
        )}
      >
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-text-secondary" />
          <span className="text-sm font-medium text-text-primary">运行状态</span>
        </div>
        <div className="flex items-center gap-2">
          <StatusIndicator />
          <ChevronDown
            className={clsx('w-4 h-4 text-text-muted transition-transform duration-150 ease-out', expanded && 'rotate-180')}
          />
        </div>
      </button>
      <div
        className="grid transition-[grid-template-rows] duration-150 ease-out"
        style={{ gridTemplateRows: expanded ? '1fr' : '0fr' }}
      >
        <div className="overflow-hidden min-h-0">
          <div className="border-t border-border" />
          <div className="p-3 space-y-1.5 text-xs">
            {rows.map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <span className="w-20 shrink-0 text-text-muted">{k}</span>
                <span className="min-w-0 text-text-primary break-words">{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
