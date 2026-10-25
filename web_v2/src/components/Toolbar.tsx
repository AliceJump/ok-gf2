/** 任务列表底部工具栏：全选 / 折叠 / 预设 / 添加 + 暂停 + 开始/停止（沿用 MXU Toolbar）。 */
import clsx from 'clsx';
import {
  CheckSquare,
  ChevronsDownUp,
  ChevronsUpDown,
  Loader2,
  Pause,
  Play,
  Plus,
  Sparkles,
  Square,
  StopCircle,
} from 'lucide-react';
import { currentWorkflow, presetsOf, useStore } from '@/store';

export function Toolbar() {
  const catalog = useStore((s) => s.catalog);
  const workflows = useStore((s) => s.workflows);
  const status = useStore((s) => s.status);
  const busy = useStore((s) => s.busy);
  const prefs = useStore((s) => s.prefs);
  const setPrefs = useStore((s) => s.setPrefs);
  const setAllExpanded = useStore((s) => s.setAllExpanded);
  const setAllEnabled = useStore((s) => s.setAllEnabled);
  const startWorkflow = useStore((s) => s.startWorkflow);
  const stop = useStore((s) => s.stop);
  const togglePause = useStore((s) => s.togglePause);

  const wf = currentWorkflow({ workflows, prefs });
  const items = wf?.items ?? [];
  const hasPresets = presetsOf(wf, catalog).length > 0;
  const allEnabled = items.length > 0 && items.every((i) => i.enabled);
  const anyChecked = items.some((i) => i.enabled);
  const anyExpanded = items.some((i) => prefs.expanded.includes(i.uid));
  const running = !!status.running && !!status.current_task;
  const paused = !!status.paused;
  const starting = !!status.starting;

  const handleStartStop = () => {
    if (running) void stop();
    else void startWorkflow();
  };

  const toolBtn =
    'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-sm transition-colors text-text-secondary hover:bg-bg-hover hover:text-text-primary disabled:text-text-muted disabled:cursor-not-allowed disabled:hover:bg-transparent';
  const toggleBtn = (on: boolean) =>
    clsx(
      'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-sm transition-colors',
      on ? 'bg-accent/10 text-accent' : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary',
    );

  return (
    <div className="flex items-center justify-between px-3 py-2 bg-bg-secondary border-t border-border">
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => setAllEnabled(!allEnabled)}
          disabled={!items.length || running}
          className={toolBtn}
          title={allEnabled ? '取消全选' : '全选'}
        >
          {allEnabled ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
          <span className="hidden sm:inline">{allEnabled ? '取消全选' : '全选'}</span>
        </button>
        <button
          type="button"
          onClick={() => setAllExpanded(!anyExpanded)}
          disabled={!items.length}
          className={toolBtn}
          title={anyExpanded ? '全部折叠' : '全部展开'}
        >
          {anyExpanded ? <ChevronsDownUp className="w-4 h-4" /> : <ChevronsUpDown className="w-4 h-4" />}
          <span className="hidden sm:inline">{anyExpanded ? '折叠' : '展开'}</span>
        </button>
        {hasPresets && (
          <button
            type="button"
            onClick={() => setPrefs({ showPresetPanel: !prefs.showPresetPanel, showAddPanel: false })}
            className={toggleBtn(prefs.showPresetPanel)}
            title="一键预设"
          >
            <Sparkles className="w-4 h-4" />
            <span className="hidden sm:inline">预设</span>
          </button>
        )}
        <button
          type="button"
          onClick={() => setPrefs({ showAddPanel: !prefs.showAddPanel, showPresetPanel: false })}
          className={toggleBtn(prefs.showAddPanel)}
          title="往这个流程里添加块"
        >
          <Plus className="w-4 h-4" />
          <span className="hidden sm:inline">添加</span>
        </button>
      </div>

      <div className="flex items-center gap-2">
        {running && (
          <button
            type="button"
            onClick={() => togglePause()}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
              paused ? 'bg-warning text-white hover:bg-warning/90' : 'bg-bg-tertiary text-text-secondary hover:bg-bg-hover',
            )}
            title={paused ? '继续执行' : '暂停执行'}
          >
            {paused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
            <span>{paused ? '继续' : '暂停'}</span>
          </button>
        )}
        <button
          type="button"
          onClick={handleStartStop}
          disabled={busy || (!running && (!anyChecked || starting))}
          className={clsx(
            'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors',
            running
              ? 'bg-error hover:bg-error/90 text-white'
              : starting
                ? 'bg-success text-white'
                : !anyChecked
                  ? 'bg-bg-active text-text-tertiary cursor-not-allowed'
                  : 'bg-accent hover:bg-accent-hover text-white',
          )}
          title={running ? `停止「${status.current_task}」` : anyChecked ? `按勾选的块启动「${wf?.label}」` : '先勾选至少一块'}
        >
          {busy || starting ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : running ? (
            <StopCircle className="w-4 h-4" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          <span>{running ? '停止' : starting ? '正在启动…' : '开始'}</span>
        </button>
      </div>
    </div>
  );
}
