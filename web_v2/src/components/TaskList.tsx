/** 当前流程里的块，按组件库的游戏板块分组显示。 */
import clsx from 'clsx';
import { AlertTriangle, ChevronDown, ListTodo, Plus, Trash2 } from 'lucide-react';
import { currentWorkflow, groupedItems, orphanItems, useStore } from '@/store';
import { TaskItem } from './TaskItem';
import { Tooltip } from './ui/Tooltip';

export function TaskList() {
  const catalog = useStore((s) => s.catalog);
  const tasks = useStore((s) => s.tasks);
  const workflows = useStore((s) => s.workflows);
  const prefs = useStore((s) => s.prefs);
  const setPrefs = useStore((s) => s.setPrefs);
  const toggleGroup = useStore((s) => s.toggleGroupCollapsed);
  const removeItem = useStore((s) => s.removeItem);
  const wf = currentWorkflow({ workflows, prefs });

  if (!catalog || !wf) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-text-muted gap-3">
        <ListTodo className="w-12 h-12 opacity-30" />
        <p className="text-sm">正在加载…</p>
      </div>
    );
  }

  const groups = groupedItems(wf, catalog, tasks);
  const orphans = orphanItems(wf, catalog, tasks);

  if (!wf.items.length) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-text-muted gap-3 p-6 text-center">
        <ListTodo className="w-12 h-12 opacity-30" />
        <p className="text-sm">「{wf.label}」还是空的</p>
        <p className="text-xs">把下面「添加」里的块加进来，勾上就会随这个流程一起跑。每一块的设置只属于这个流程。</p>
        <button
          type="button"
          onClick={() => setPrefs({ showAddPanel: true })}
          className="mt-1 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm bg-accent text-white hover:bg-accent-hover transition-colors"
        >
          <Plus className="w-4 h-4" />
          添加块
        </button>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto overflow-x-hidden p-3">
      <div key={wf.id} className="space-y-3 animate-fade-in">
        {wf.desc && <p className="px-1 text-xs text-text-muted">{wf.desc}</p>}
        {groups.map(({ group: g, items }) => {
          const collapseId = `${wf.id}:${g.id}`;
          const isCollapsed = prefs.collapsedGroups.includes(collapseId);
          // 只数有开关的块（子项 / 整任务），触发任务按后端的启用状态
          const togglable = items.filter(({ component }) => tasks.some((x) => x.class_name === component.task));
          const enabledCount = togglable.filter(({ item, component }) => {
            const t = tasks.find((x) => x.class_name === component.task)!;
            return t.trigger ? t.enabled : item.enabled;
          }).length;
          return (
            <section key={g.id}>
              <Tooltip content={g.desc} side="right">
                <button
                  type="button"
                  onClick={() => toggleGroup(collapseId)}
                  className="w-full flex items-center gap-2 px-1 py-1 mb-1.5 text-left select-none group/head"
                >
                  <span className="text-base leading-none w-5 text-center">{g.icon}</span>
                  <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">{g.label}</span>
                  <span className="text-[11px] text-text-muted">
                    {enabledCount}/{togglable.length}
                  </span>
                  <span className="flex-1 h-px bg-border mx-1" />
                  <ChevronDown
                    className={clsx(
                      'w-4 h-4 text-text-muted transition-transform duration-150',
                      isCollapsed && '-rotate-90',
                    )}
                  />
                </button>
              </Tooltip>
              <div
                className="grid transition-[grid-template-rows] duration-150 ease-out"
                style={{ gridTemplateRows: isCollapsed ? '0fr' : '1fr' }}
              >
                <div className={clsx('min-h-0', isCollapsed ? 'overflow-hidden' : 'overflow-visible')}>
                  <div className="space-y-2">
                    {items.map(({ item, component }) => (
                      <TaskItem
                        key={item.uid}
                        workflow={wf}
                        item={item}
                        component={component}
                        task={tasks.find((t) => t.class_name === component.task)}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </section>
          );
        })}
        {orphans.length > 0 && (
          <section>
            <div className="flex items-center gap-2 px-1 py-1 mb-1.5 text-xs font-semibold text-warning">
              <AlertTriangle className="w-4 h-4" />
              目录里已经没有这些块
            </div>
            <div className="space-y-2">
              {orphans.map((item) => (
                <div key={item.uid} className="flex items-center gap-2 p-3 rounded-lg border border-warning/40 bg-warning/5 text-sm text-text-secondary">
                  <span className="flex-1 truncate">{item.component}</span>
                  <button
                    type="button"
                    onClick={() => removeItem(item.uid)}
                    className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-error transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    移出
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
