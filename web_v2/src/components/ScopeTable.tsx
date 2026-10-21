/** 设置页「阵容与助战」里的各场景一览：哪些流程的哪些块单独设了编队 / 助战。 */
import clsx from 'clsx';
import { allComponents, lineupScopes, scopeState, useStore } from '@/store';

export function ScopeTable() {
  const settings = useStore((s) => s.settings);
  const catalog = useStore((s) => s.catalog);
  const tasks = useStore((s) => s.tasks);
  const workflows = useStore((s) => s.workflows);
  const scopes = lineupScopes(settings);
  if (!scopes.length || !catalog) return null;
  const comps = allComponents(catalog, tasks);

  // 每个场景：哪些流程里的块单独设置了
  const overrides = (scope: string) => {
    const out: { workflow: string; block: string; preset: string; support: string | null }[] = [];
    for (const wf of workflows)
      for (const item of wf.items) {
        const comp = comps.find((c) => c.id === item.component);
        if (!comp?.lineup_scopes?.includes(scope)) continue;
        const st = scopeState(settings, scope, item.lineup);
        if (st?.overridden) out.push({ workflow: wf.label, block: comp.label, preset: st.preset, support: st.support === '沿用全局' ? null : st.support });
      }
    return out;
  };

  return (
    <div className="pt-2">
      <div className="text-sm text-text-secondary">各场景单独设置</div>
      <div className="text-xs text-text-muted mt-0.5">
        这里是全局值；每个流程里块的「阵容」卡片可以单独覆盖，只对那个流程生效。下面列出谁覆盖了。
      </div>
      <table className="w-full mt-2 text-xs border-collapse">
        <thead>
          <tr className="text-text-muted">
            <th className="text-left font-medium px-2 py-1.5 border-b border-border">场景</th>
            <th className="text-left font-medium px-2 py-1.5 border-b border-border">全局编队</th>
            <th className="text-left font-medium px-2 py-1.5 border-b border-border">单独设置的流程</th>
          </tr>
        </thead>
        <tbody>
          {scopes.map((scope) => {
            const st = scopeState(settings, scope)!;
            const ov = overrides(scope);
            return (
              <tr key={scope} className={clsx(ov.length && 'bg-accent/5')}>
                <td className={clsx('px-2 py-1.5 border-b border-border/60 text-text-primary align-top', ov.length && 'border-l-2 border-l-accent')}>{scope}</td>
                <td className="px-2 py-1.5 border-b border-border/60 text-text-muted align-top">
                  {st.globalPreset || '不切'}
                  {st.support !== null && `，助战${st.globalSupport ? '开' : '关'}`}
                </td>
                <td className="px-2 py-1.5 border-b border-border/60 align-top">
                  {ov.length === 0 ? (
                    <span className="text-text-muted">—</span>
                  ) : (
                    <div className="space-y-0.5">
                      {ov.map((o, i) => (
                        <div key={i} className="text-text-primary">
                          <span className="text-accent font-medium">{o.workflow}</span> · {o.block}：
                          {o.preset ? `编队「${o.preset}」` : '编队沿用'}
                          {o.support ? `，助战${o.support}` : ''}
                        </div>
                      ))}
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
