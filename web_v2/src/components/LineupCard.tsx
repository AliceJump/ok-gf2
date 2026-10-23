/** 块里的「阵容」卡片：这一块在这个流程里的编队 / 借助战，单独设置或沿用全局。 */
import { useEffect, useState } from 'react';
import clsx from 'clsx';
import { RotateCcw, Users } from 'lucide-react';
import type { WorkflowItem } from '@/api';
import { SUPPORT_INHERIT, scopeState, useStore } from '@/store';
import { TextInput } from './FormControls';

export function LineupCard({ scope, item, disabled }: { scope: string; item: WorkflowItem; disabled?: boolean }) {
  const settings = useStore((s) => s.settings);
  const setItemLineup = useStore((s) => s.setItemLineup);
  const st = scopeState(settings, scope, item.lineup);
  const [draft, setDraft] = useState(st?.preset ?? '');
  useEffect(() => setDraft(st?.preset ?? ''), [st?.preset]);
  if (!st) return null;
  const presetKey = `${scope}编队`;
  const supportKey = `${scope}助战`;

  const choices: [string, string][] = [
    [SUPPORT_INHERIT, `沿用全局（${st.globalSupport ? '开' : '关'}）`],
    ['开', '开'],
    ['关', '关'],
  ];

  return (
    <div
      className={clsx(
        'rounded-lg border p-3 space-y-3 bg-bg-secondary',
        st.overridden ? 'border-accent' : 'border-border',
      )}
    >
      <div className="flex items-center gap-2">
        <Users className="w-4 h-4 text-accent flex-shrink-0" />
        <span className="text-sm font-medium text-text-primary">阵容 · {scope}</span>
        {st.overridden && (
          <span className="px-1.5 py-0.5 text-[11px] rounded-full border border-accent text-accent">已单独设置</span>
        )}
        <button
          type="button"
          disabled={disabled || !st.overridden}
          onClick={() => setItemLineup(item.uid, [[presetKey, null], [supportKey, null]])}
          className="ml-auto inline-flex items-center gap-1 text-xs text-text-muted hover:text-accent transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:text-text-muted"
        >
          <RotateCcw className="w-3 h-3" />
          恢复全局
        </button>
      </div>

      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1 max-w-[60%]">
          <div className="text-sm text-text-secondary">编队</div>
          <div className="text-xs text-text-muted mt-0.5">整备室配置里的编队名，留空沿用全局；只对这个流程生效</div>
        </div>
        <TextInput
          className="w-[36%] ml-auto"
          value={draft}
          onChange={setDraft}
          disabled={disabled}
          placeholder={`沿用全局（${st.globalPreset || '不切编队'}）`}
          onCommit={(v) => {
            if (v.trim() !== st.preset) setItemLineup(item.uid, [[presetKey, v.trim() || null]]);
          }}
        />
      </div>

      {st.support !== null && (
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1 max-w-[60%]">
            <div className="text-sm text-text-secondary">借好友助战</div>
            <div className="text-xs text-text-muted mt-0.5">这一场景实际：{st.effectiveSupport ? '借' : '不借'}</div>
          </div>
          <div className="ml-auto inline-flex rounded-md border border-border overflow-hidden">
            {choices.map(([value, label]) => (
              <button
                key={value}
                type="button"
                disabled={disabled}
                onClick={() =>
                  st.support !== value && setItemLineup(item.uid, [[supportKey, value === SUPPORT_INHERIT ? null : value]])
                }
                className={clsx(
                  'px-2.5 py-1 text-xs transition-colors border-l border-border first:border-l-0',
                  st.support === value ? 'bg-accent text-white' : 'bg-bg-primary text-text-secondary hover:bg-bg-hover',
                  disabled && 'opacity-60 cursor-not-allowed',
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
