/** 顶栏（对应 MXU TabBar）：一个流程一个页签，可新建 / 双击改名 / 右键菜单 / 关闭；右边主题切换和设置。 */
import { useEffect, useRef, useState } from 'react';
import clsx from 'clsx';
import { ChevronLeft, ChevronRight, Copy, Edit3, Moon, Plus, Settings, Sun, X, XCircle } from 'lucide-react';
import { currentWorkflow, runningWorkflow, useStore } from '@/store';
import { resolveThemeMode } from '@/themes';
import { StatusIndicator } from './StatusPanel';
import { ConfirmDialog } from './ui/Modal';
import { ContextMenu, useContextMenu, type MenuItem } from './ui/ContextMenu';

export function TopBar() {
  const page = useStore((s) => s.page);
  const setPage = useStore((s) => s.setPage);
  const title = useStore((s) => s.title);
  const themePreference = useStore((s) => s.themePreference);
  const setThemePreference = useStore((s) => s.setThemePreference);
  const status = useStore((s) => s.status);
  const catalog = useStore((s) => s.catalog);
  const tasks = useStore((s) => s.tasks);
  const workflows = useStore((s) => s.workflows);
  const runningWorkflowId = useStore((s) => s.runningWorkflowId);
  const prefs = useStore((s) => s.prefs);
  const setWorkflow = useStore((s) => s.setWorkflow);
  const addWorkflow = useStore((s) => s.addWorkflow);
  const duplicateWorkflow = useStore((s) => s.duplicateWorkflow);
  const renameWorkflow = useStore((s) => s.renameWorkflow);
  const moveWorkflow = useStore((s) => s.moveWorkflow);
  const removeWorkflow = useStore((s) => s.removeWorkflow);
  const mode = resolveThemeMode(themePreference);
  const current = currentWorkflow({ workflows, prefs });
  const runningWf = runningWorkflow({ workflows, runningWorkflowId, status, tasks, catalog });

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [closing, setClosing] = useState<{ id: string; label: string } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { state: menu, showAt, hide } = useContextMenu();

  useEffect(() => {
    if (editingId) inputRef.current?.select();
  }, [editingId]);

  const startEdit = (id: string, label: string) => {
    setEditingId(id);
    setEditName(label);
  };
  const saveEdit = () => {
    if (editingId) renameWorkflow(editingId, editName);
    setEditingId(null);
  };

  const openMenu = (e: React.MouseEvent, id: string, label: string) => {
    e.preventDefault();
    const idx = workflows.findIndex((w) => w.id === id);
    const items: MenuItem[] = [
      { id: 'new', label: '新建流程', icon: Plus, onClick: () => startEdit(addWorkflow(), '新流程') },
      { id: 'dup', label: '复制这个流程', icon: Copy, onClick: () => duplicateWorkflow(id) },
      { id: 'rename', label: '重命名', icon: Edit3, onClick: () => startEdit(id, label) },
      { id: 'd1', label: '', divider: true },
      { id: 'left', label: '左移', icon: ChevronLeft, disabled: idx <= 0, onClick: () => moveWorkflow(id, -1) },
      { id: 'right', label: '右移', icon: ChevronRight, disabled: idx >= workflows.length - 1, onClick: () => moveWorkflow(id, 1) },
      { id: 'd2', label: '', divider: true },
      { id: 'close', label: '删除流程', icon: XCircle, danger: true, disabled: workflows.length <= 1, onClick: () => setClosing({ id, label }) },
    ];
    showAt({ x: e.clientX, y: e.clientY }, items);
  };

  return (
    <div className="flex items-center h-10 bg-bg-secondary border-b border-border select-none shrink-0">
      <div className="flex-1 flex items-center h-full overflow-x-auto overflow-y-hidden">
        {workflows.map((wf) => {
          const active = page === 'main' && current?.id === wf.id;
          const editing = editingId === wf.id;
          return (
            <div
              key={wf.id}
              onClick={() => {
                setWorkflow(wf.id);
                setPage('main');
              }}
              onDoubleClick={(e) => {
                e.stopPropagation();
                startEdit(wf.id, wf.label);
              }}
              onContextMenu={(e) => openMenu(e, wf.id, wf.label)}
              title={wf.desc}
              className={clsx(
                'group/tab flex items-center gap-1.5 h-full pl-3 pr-1.5 cursor-pointer border-r border-border min-w-[110px] max-w-[200px] text-sm',
                active
                  ? 'bg-bg-primary text-accent border-b-2 border-b-accent'
                  : 'bg-bg-tertiary text-text-secondary hover:bg-bg-hover border-b-2 border-b-transparent',
              )}
            >
              {runningWf?.id === wf.id && (
                <span className="w-2 h-2 rounded-full bg-accent task-running-indicator flex-shrink-0" />
              )}
              {wf.icon && <span className="text-sm leading-none flex-shrink-0">{wf.icon}</span>}
              {editing ? (
                <input
                  ref={inputRef}
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onBlur={saveEdit}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') saveEdit();
                    if (e.key === 'Escape') setEditingId(null);
                  }}
                  onClick={(e) => e.stopPropagation()}
                  className="w-[110px] px-1 py-0.5 text-sm bg-bg-primary border border-accent rounded outline-none text-text-primary"
                />
              ) : (
                <span className="truncate">{wf.label}</span>
              )}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setClosing({ id: wf.id, label: wf.label });
                }}
                disabled={workflows.length <= 1}
                className={clsx(
                  'ml-auto p-0.5 rounded transition-colors flex-shrink-0',
                  'opacity-0 group-hover/tab:opacity-100 hover:bg-bg-active text-text-muted hover:text-text-primary',
                  'disabled:opacity-0',
                )}
                title="删除流程"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
        <button
          type="button"
          onClick={() => startEdit(addWorkflow(), '新流程')}
          className="flex items-center justify-center h-full px-2.5 text-text-muted hover:text-accent hover:bg-bg-hover transition-colors"
          title="新建流程"
        >
          <Plus className="w-4 h-4" />
        </button>
        <div className="px-3">
          <StatusIndicator />
        </div>
      </div>

      <div className="hidden md:block px-4 text-sm font-medium text-text-secondary whitespace-nowrap">{title}</div>

      <div className="flex items-center gap-1 px-2">
        <button
          type="button"
          onClick={() => setThemePreference(mode === 'light' ? 'dark' : 'light')}
          className="p-2 rounded-md hover:bg-bg-hover transition-colors"
          title={mode === 'light' ? '切换到深色' : '切换到浅色'}
        >
          {mode === 'light' ? <Moon className="w-4 h-4 text-text-secondary" /> : <Sun className="w-4 h-4 text-text-secondary" />}
        </button>
        <button
          type="button"
          onClick={() => setPage(page === 'settings' ? 'main' : 'settings')}
          className={clsx('p-2 rounded-md transition-colors', page === 'settings' ? 'bg-accent/10 text-accent' : 'hover:bg-bg-hover text-text-secondary')}
          title="设置"
        >
          <Settings className="w-4 h-4" />
        </button>
      </div>

      {menu.open && <ContextMenu items={menu.items} position={menu.position} onClose={hide} />}
      <ConfirmDialog
        open={!!closing}
        title="删除流程"
        message={`删除「${closing?.label ?? ''}」？这个流程里的块和它们的设置都会一起删掉。`}
        confirmText="删除"
        destructive
        onCancel={() => setClosing(null)}
        onConfirm={() => {
          if (closing) removeWorkflow(closing.id);
          setClosing(null);
        }}
      />
    </div>
  );
}
