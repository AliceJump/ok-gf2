/** 流程里的一块（沿用 MXU TaskItem 的结构）：复选框 + 名称 + 选项预览 + 展开面板 + 移出。 */
import { useMemo, useState } from 'react';
import clsx from 'clsx';
import { ChevronRight, Play, RotateCcw, Trash2, Zap, ZapOff } from 'lucide-react';
import type { CatalogComponent, ConfigField, TaskInfo, Workflow, WorkflowItem } from '@/api';
import { entryOptionKeys, itemChangedCount, itemFields, taskProgress, useStore } from '@/store';
import { Checkbox } from './ui/Checkbox';
import { ConfirmDialog } from './ui/Modal';
import { OptionList } from './OptionEditor';
import { Tooltip } from './ui/Tooltip';
import { LineupCard } from './LineupCard';

function truncate(s: string, n: number) {
  return s.length > n ? `${s.slice(0, n)}…` : s;
}

function PreviewTag({ field }: { field: ConfigField }) {
  const v = field.value;
  const text = Array.isArray(v) ? `${v.length} 项` : v === null || v === undefined ? '' : String(v);
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs rounded text-text-tertiary max-w-[140px]"
      title={`${field.key}: ${text}`}
    >
      {field.kind === 'boolean' ? (
        <>
          <span className="truncate">{truncate(field.key, 6)}</span>
          <span
            className={clsx(
              'w-1.5 h-1.5 rounded-full flex-shrink-0',
              v ? 'bg-success/70' : 'bg-text-muted/50',
            )}
          />
        </>
      ) : (
        <>
          <span className="truncate flex-shrink-0">{truncate(field.key, 4)}</span>
          <span className="flex-shrink-0">:</span>
          <span className="truncate">{truncate(text, 6)}</span>
        </>
      )}
    </span>
  );
}

export function TaskItem({
  workflow,
  item,
  component,
  task,
}: {
  workflow: Workflow;
  item: WorkflowItem;
  component: CatalogComponent;
  task: TaskInfo | undefined;
}) {
  const expanded = useStore((s) => s.prefs.expanded.includes(item.uid));
  const toggleExpanded = useStore((s) => s.toggleExpanded);
  const setItemEnabled = useStore((s) => s.setItemEnabled);
  const setItemConfig = useStore((s) => s.setItemConfig);
  const resetItem = useStore((s) => s.resetItem);
  const removeItem = useStore((s) => s.removeItem);
  const runItem = useStore((s) => s.runItem);
  const taskAction = useStore((s) => s.taskAction);
  const status = useStore((s) => s.status);
  const busy = useStore((s) => s.busy);
  const justAdded = useStore((s) => s.justAdded === item.uid);
  const di = useMemo(() => taskProgress(task), [task]);
  const [confirmReset, setConfirmReset] = useState(false);
  const scopes = component.lineup_scopes ?? [];

  const isTrigger = !!task?.trigger;
  const enabled = isTrigger ? !!task?.enabled : item.enabled;
  const optionKeys = entryOptionKeys(component, task);
  const fields = task ? itemFields(item, task) : [];
  const optionFields = optionKeys.map((k) => fields.find((f) => f.key === k)).filter((f): f is ConfigField => !!f);
  const canExpand = !!task && (optionFields.length > 0 || scopes.length > 0 || !!component.doc || !!task.description);
  const executorRunning = !!status.running && !!status.current_task;
  const changedKeys = itemChangedCount(item, component, task);

  // 运行状态：子项看「当前任务」是否就是它；整任务块看任务自己的 running
  const runStatus: 'idle' | 'running' | 'done' | 'retry' = (() => {
    if (!task) return 'idle';
    if (!component.enable_key) return task.running ? 'running' : 'idle';
    if (executorRunning && status.current_task === task.name && di.raw.current_task === component.enable_key) return 'running';
    if (di.done.includes(component.enable_key)) return 'done';
    if (di.retry.includes(component.enable_key)) return 'retry';
    return 'idle';
  })();

  const handleCheckbox = () => {
    if (!task) return;
    if (isTrigger) void taskAction(task.name, task.enabled ? 'disable' : 'enable');
    else setItemEnabled(item.uid, !item.enabled);
  };

  return (
    <div
      className={clsx(
        'group bg-bg-secondary rounded-lg border border-border transition-shadow relative overflow-hidden',
        runStatus === 'running' && 'task-item-running',
        justAdded && 'animate-task-slide-in',
      )}
    >
      {runStatus !== 'idle' && (
        <div
          className={clsx(
            'absolute left-0 top-0 bottom-0 w-1.5',
            runStatus === 'running' && 'bg-accent',
            runStatus === 'done' && 'bg-success/60',
            runStatus === 'retry' && 'bg-warning',
          )}
          title={runStatus === 'running' ? '运行中' : runStatus === 'done' ? '今日已完成' : '今日待重试'}
        />
      )}

      <div className="flex items-center gap-2 p-3 pl-4">
        {!task ? (
          <Tooltip content="任务类未注册">
            <span className="w-4 h-4 flex items-center justify-center text-text-muted">
              <Play className="w-3 h-3" />
            </span>
          </Tooltip>
        ) : (
          <Checkbox
            checked={enabled}
            disabled={executorRunning && !isTrigger}
            title={isTrigger ? (enabled ? '停用触发任务' : '启用触发任务') : enabled ? '取消勾选' : `勾选，随「${workflow.label}」一起跑`}
            onClick={handleCheckbox}
          />
        )}

        <div className="flex-1 flex items-center min-w-0">
          <div
            className={clsx('flex items-center gap-1 min-w-0 overflow-hidden', task && 'cursor-pointer')}
            onClick={() => task && handleCheckbox()}
          >
            <span className={clsx('min-w-0 text-sm font-medium truncate', enabled || !task ? 'text-text-primary' : 'text-text-muted')}>
              {component.label}
            </span>
          </div>

          {!task && <span className="ml-2 px-1.5 py-0.5 text-xs rounded bg-warning/10 text-warning">未注册</span>}
          {isTrigger && (
            <span className="ml-2 inline-flex items-center gap-1 px-1.5 py-0.5 text-xs rounded bg-bg-tertiary text-text-tertiary">
              {task?.enabled ? <Zap className="w-3 h-3 text-accent" /> : <ZapOff className="w-3 h-3" />}
              触发任务
            </span>
          )}
          {changedKeys > 0 && (
            <Tooltip content="这一块在这个流程里有单独改过的设置，不影响别的流程">
              <span className="ml-2 px-1.5 py-0.5 text-[11px] rounded-full border border-accent/60 text-accent whitespace-nowrap">已单独设置</span>
            </Tooltip>
          )}
          {runStatus === 'done' && (
            <span className="ml-2 px-1.5 py-0.5 text-xs rounded bg-accent/10 text-accent whitespace-nowrap">今日已完成</span>
          )}
          {runStatus === 'retry' && (
            <span className="ml-2 px-1.5 py-0.5 text-xs rounded bg-warning/10 text-warning whitespace-nowrap">待重试</span>
          )}

          <div
            onClick={() => canExpand && toggleExpanded(item.uid)}
            className={clsx('flex-1 min-w-0 flex items-center self-stretch min-h-[28px]', canExpand && 'cursor-pointer')}
            title={canExpand ? (expanded ? '收起' : '展开') : undefined}
          >
            {!expanded && (
              <div className="flex-1 flex items-center gap-1.5 mx-2 overflow-hidden">
                {optionFields.slice(0, 4).map((f) => (
                  <PreviewTag key={f.key} field={f} />
                ))}
              </div>
            )}
            <div className="flex shrink-0 items-center justify-end gap-1 pl-2 ml-auto">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  removeItem(item.uid);
                }}
                disabled={executorRunning}
                className="p-1 rounded text-text-muted/70 hover:text-error hover:bg-error/10 transition-colors disabled:opacity-30 disabled:hover:text-text-muted/70 disabled:hover:bg-transparent"
                title="从这个流程移出"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
              {canExpand && (
                <ChevronRight
                  className={clsx('w-4 h-4 text-text-secondary transition-transform duration-150 ease-out', expanded && 'rotate-90')}
                />
              )}
            </div>
          </div>
        </div>

        {task && !component.enable_key && !isTrigger && (
          <button
            type="button"
            onClick={() => runItem(item.uid)}
            disabled={executorRunning || busy}
            className={clsx(
              'flex items-center gap-1 px-2 py-1 rounded-md text-xs transition-colors shrink-0',
              executorRunning || busy ? 'text-text-muted cursor-not-allowed' : 'bg-accent/10 text-accent hover:bg-accent hover:text-white',
            )}
            title={`只跑这一块（按这个流程里的设置）`}
          >
            <Play className="w-3 h-3" />
            运行
          </button>
        )}
      </div>

      {canExpand && (
        <div
          className="grid transition-[grid-template-rows] duration-150 ease-out"
          style={{ gridTemplateRows: expanded ? '1fr' : '0fr' }}
        >
          <div className={clsx('min-h-0', expanded ? 'overflow-visible' : 'overflow-hidden')}>
            <div className="border-t border-border bg-bg-tertiary p-3 rounded-b-lg">
              {(component.doc || task?.description) && (
                <div className={clsx('text-xs text-text-secondary whitespace-pre-line', optionFields.length > 0 && 'mb-4')}>
                  {component.doc || task?.description}
                </div>
              )}
              {task && optionFields.length > 0 && (
                <OptionList
                  fields={fields}
                  keys={optionKeys}
                  disabled={executorRunning}
                  onChange={(key, value) => setItemConfig(item.uid, key, value)}
                />
              )}
              {task && scopes.length > 0 && (
                <div className={clsx('space-y-3', optionFields.length > 0 && 'mt-4')}>
                  {scopes.map((scope) => (
                    <LineupCard key={scope} scope={scope} item={item} disabled={executorRunning} />
                  ))}
                </div>
              )}
              {task && (
                <div className="mt-3 flex items-center justify-end gap-4">
                  <button
                    type="button"
                    onClick={() => removeItem(item.uid)}
                    disabled={executorRunning}
                    className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-error transition-colors disabled:opacity-40"
                  >
                    <Trash2 className="w-3 h-3" />
                    从「{workflow.label}」移出
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmReset(true)}
                    disabled={executorRunning || changedKeys === 0}
                    className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-accent transition-colors disabled:opacity-40 disabled:hover:text-text-muted"
                  >
                    <RotateCcw className="w-3 h-3" />
                    恢复默认值
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmReset}
        title="恢复默认"
        message={`把「${component.label}」在「${workflow.label}」里的选项和阵容恢复成默认值？别的流程里的同一块不受影响。`}
        confirmText="恢复"
        destructive
        onCancel={() => setConfirmReset(false)}
        onConfirm={() => {
          setConfirmReset(false);
          resetItem(item.uid);
        }}
      />
    </div>
  );
}
