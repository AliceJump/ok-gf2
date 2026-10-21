/** 设置页：左侧目录 + 右侧分区（外观 / 全局设置 / 框架设置 / 关于），沿用 MXU SettingsPage。 */
import { useEffect, useMemo, useRef, useState } from 'react';
import clsx from 'clsx';
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Info,
  LayoutGrid,
  Monitor,
  Moon,
  Palette,
  RotateCcw,
  Settings2,
  Sun,
  type LucideIcon,
} from 'lucide-react';
import { LINEUP_GROUP, isScopeKey, useStore, taskByClass } from '@/store';
import { ScopeTable } from './ScopeTable';
import { accentList, type ThemePreference } from '@/themes';
import { OptionList } from './OptionEditor';
import { ConfirmDialog } from './ui/Modal';

interface TocItem {
  id: string;
  label: string;
  icon: LucideIcon;
}

function Section({
  id,
  icon: Icon,
  title,
  children,
}: {
  id: string;
  icon: LucideIcon;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="space-y-4 scroll-mt-4">
      <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider flex items-center gap-2">
        <Icon className="w-4 h-4" />
        {title}
      </h2>
      {children}
    </section>
  );
}

function AppearanceSection() {
  const themePreference = useStore((s) => s.themePreference);
  const setThemePreference = useStore((s) => s.setThemePreference);
  const accent = useStore((s) => s.accent);
  const setAccent = useStore((s) => s.setAccent);
  const modes: { value: ThemePreference; label: string; icon: LucideIcon }[] = [
    { value: 'light', label: '浅色', icon: Sun },
    { value: 'dark', label: '深色', icon: Moon },
    { value: 'system', label: '跟随系统', icon: Monitor },
  ];
  return (
    <Section id="section-appearance" icon={Palette} title="外观">
      <div className="bg-bg-secondary rounded-xl p-4 border border-border space-y-4">
        <div>
          <div className="font-medium text-text-primary">主题模式</div>
          <div className="grid grid-cols-3 gap-2 mt-2">
            {modes.map((m) => (
              <button
                key={m.value}
                type="button"
                onClick={() => setThemePreference(m.value)}
                className={clsx(
                  'flex items-center justify-center gap-2 px-3 py-2 rounded-lg border text-sm transition-colors',
                  themePreference === m.value
                    ? 'border-accent bg-accent/10 text-accent'
                    : 'border-border bg-bg-tertiary text-text-secondary hover:bg-bg-hover',
                )}
              >
                <m.icon className="w-4 h-4" />
                {m.label}
              </button>
            ))}
          </div>
        </div>
        <div className="pt-4 border-t border-border">
          <div className="font-medium text-text-primary">强调色</div>
          <p className="text-xs text-text-muted mt-0.5">和 MXU 同一组预设。</p>
          <div className="grid grid-cols-3 sm:grid-cols-5 gap-2 mt-2">
            {accentList().map((a) => (
              <button
                key={a.name}
                type="button"
                onClick={() => setAccent(a.name)}
                className={clsx(
                  'flex items-center gap-2 px-2.5 py-2 rounded-lg border text-sm transition-colors text-left',
                  accent === a.name ? 'border-accent bg-accent/10' : 'border-border bg-bg-tertiary hover:bg-bg-hover',
                )}
              >
                <span className="w-5 h-5 rounded-full flex items-center justify-center shrink-0" style={{ backgroundColor: a.color }}>
                  {accent === a.name && <Check className="w-3 h-3 text-white" strokeWidth={3} />}
                </span>
                <span className="truncate text-text-primary">{a.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </Section>
  );
}

function Card({
  title,
  desc,
  onReset,
  children,
  defaultOpen = true,
}: {
  title: string;
  desc?: string;
  onReset?: () => void;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}
      className="rounded-xl border border-border bg-bg-secondary overflow-hidden"
    >
      <summary className="list-none cursor-pointer select-none px-4 py-3 flex items-center justify-between gap-3 hover:bg-bg-hover transition-colors">
        <div className="flex items-center gap-3 min-w-0">
          <LayoutGrid className="w-5 h-5 text-accent flex-shrink-0" />
          <div className="min-w-0">
            <div className="text-sm font-semibold text-text-primary truncate">{title}</div>
            {desc && <div className="text-xs text-text-secondary line-clamp-2 whitespace-pre-line">{desc}</div>}
          </div>
        </div>
        <span className={clsx('flex-shrink-0 text-text-secondary transition-transform duration-200', open ? 'rotate-90' : 'rotate-0')}>
          <ChevronRight className="w-4 h-4" />
        </span>
      </summary>
      <div className="px-4 pb-4 pt-2 space-y-3">
        <div className="rounded-lg border border-border/60 bg-bg-primary/60 p-3">{children}</div>
        {onReset && (
          <div className="flex justify-end">
            <button
              type="button"
              onClick={onReset}
              className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-accent transition-colors"
            >
              <RotateCcw className="w-3 h-3" />
              恢复默认
            </button>
          </div>
        )}
      </div>
    </details>
  );
}

export function SettingsPage() {
  const setPage = useStore((s) => s.setPage);
  const catalog = useStore((s) => s.catalog);
  const tasks = useStore((s) => s.tasks);
  const settings = useStore((s) => s.settings);
  const setTaskConfig = useStore((s) => s.setTaskConfig);
  const setSetting = useStore((s) => s.setSetting);
  const resetSetting = useStore((s) => s.resetSetting);
  const resetTaskConfig = useStore((s) => s.resetTaskConfig);
  const [pendingReset, setPendingReset] = useState<{ kind: 'task' | 'group'; name: string } | null>(null);
  const [active, setActive] = useState('section-appearance');
  const scrollRef = useRef<HTMLDivElement>(null);

  const toc: TocItem[] = useMemo(
    () => [
      { id: 'section-appearance', label: '外观', icon: Palette },
      { id: 'section-global', label: '全局设置', icon: LayoutGrid },
      { id: 'section-framework', label: '框架设置', icon: Settings2 },
      { id: 'section-about', label: '关于', icon: Info },
    ],
    [],
  );

  useEffect(() => {
    const root = scrollRef.current;
    if (!root) return;
    const onScroll = () => {
      let cur = toc[0].id;
      for (const item of toc) {
        const el = document.getElementById(item.id);
        if (el && el.getBoundingClientRect().top - root.getBoundingClientRect().top <= 80) cur = item.id;
      }
      setActive(cur);
    };
    root.addEventListener('scroll', onScroll);
    return () => root.removeEventListener('scroll', onScroll);
  }, [toc]);

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="flex-1 flex min-h-0 bg-bg-primary">
      <nav className="w-44 shrink-0 border-r border-border bg-bg-secondary p-3 space-y-1 overflow-y-auto">
        <button
          type="button"
          onClick={() => setPage('main')}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors mb-2"
        >
          <ArrowLeft className="w-4 h-4" />
          返回任务
        </button>
        {toc.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => scrollTo(item.id)}
            className={clsx(
              'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors text-left',
              active === item.id ? 'bg-accent text-white' : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary',
            )}
          >
            <item.icon className="w-4 h-4 flex-shrink-0" />
            <span className="truncate">{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="flex-1 overflow-y-auto" ref={scrollRef}>
        <div className="max-w-2xl mx-auto p-6 space-y-8">
          <AppearanceSection />

          <Section id="section-global" icon={LayoutGrid} title="全局设置">
            <p className="text-xs text-text-muted -mt-2">对整轮日常都生效的项，从各板块里抽出来放这。</p>
            <div className="space-y-4">
              {(catalog?.global_sections ?? []).map((sec) => {
                const task = taskByClass({ tasks }, sec.task);
                if (!task) return null;
                return (
                  <Card
                    key={sec.label}
                    title={sec.label}
                    desc={sec.desc}
                    onReset={() => setPendingReset({ kind: 'task', name: task.name })}
                  >
                    <OptionList
                      fields={task.config}
                      keys={sec.keys}
                      onChange={(k, v) => setTaskConfig(task.name, k, v).catch(() => {})}
                    />
                  </Card>
                );
              })}
            </div>
          </Section>

          <Section id="section-framework" icon={Settings2} title="框架设置">
            <p className="text-xs text-text-muted -mt-2">ok-script 框架层的设置（窗口、截图、阵容与助战等）。</p>
            <div className="space-y-4">
              {settings.length === 0 && <div className="text-sm text-text-muted">正在加载…</div>}
              {settings.map((g) => (
                <Card
                  key={g.name}
                  title={g.name}
                  desc={g.description}
                  defaultOpen={false}
                  onReset={() => setPendingReset({ kind: 'group', name: g.name })}
                >
                  <OptionList
                    fields={g.fields}
                    keys={g.fields.map((f) => f.key).filter((k) => g.name !== LINEUP_GROUP || !isScopeKey(settings, k))}
                    onChange={(k, v) => setSetting(g.name, k, v)}
                  />
                  {g.name === LINEUP_GROUP && <ScopeTable />}
                </Card>
              ))}
            </div>
          </Section>

          <Section id="section-about" icon={Info} title="关于">
            <div className="bg-bg-secondary rounded-xl p-4 border border-border text-sm text-text-secondary space-y-2">
              <p>
                <span className="font-medium text-text-primary">少前2 自动化</span>，基于 ok-script 的少女前线2：追放 日常脚本。
              </p>
              <p>
                界面样式与组件沿用{' '}
                <a className="text-accent hover:underline" href="https://github.com/MistEO/MXU" target="_blank" rel="noreferrer">
                  MXU
                </a>
                （AGPL-3.0）。配置改动即时写回 configs/，不用点保存。
              </p>
            </div>
          </Section>
        </div>
      </div>

      <ConfirmDialog
        open={pendingReset !== null}
        title="恢复默认"
        message={pendingReset ? `把「${pendingReset.name}」的全部选项恢复默认？` : ''}
        confirmText="恢复"
        destructive
        onCancel={() => setPendingReset(null)}
        onConfirm={() => {
          if (!pendingReset) return;
          if (pendingReset.kind === 'task') void resetTaskConfig(pendingReset.name);
          else void resetSetting(pendingReset.name);
          setPendingReset(null);
        }}
      />
    </div>
  );
}
