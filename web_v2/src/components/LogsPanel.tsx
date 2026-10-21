/** 运行日志卡片（沿用 MXU LogsPanel）。 */
import { Fragment, useEffect, useRef, useState } from 'react';
import clsx from 'clsx';
import { ChevronDown, Eraser, Filter } from 'lucide-react';
import { useStore } from '@/store';

const LEVELS = [
  { value: 'ALL', label: '全部' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ERROR', label: 'ERROR' },
];

function levelColor(level: string) {
  if (level === 'ERROR' || level === 'CRITICAL') return 'text-error';
  if (level === 'WARNING') return 'text-warning';
  return 'text-text-primary';
}

export function LogsPanel() {
  const logs = useStore((s) => s.logs);
  const logLevel = useStore((s) => s.logLevel);
  const logQuery = useStore((s) => s.logQuery);
  const setLogFilter = useStore((s) => s.setLogFilter);
  const clearLogs = useStore((s) => s.clearLogs);
  const sidePanelExpanded = useStore((s) => s.prefs.sidePanelExpanded);
  const setPrefs = useStore((s) => s.setPrefs);
  const [showFilter, setShowFilter] = useState(false);
  const [query, setQuery] = useState(logQuery);
  const containerRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);

  useEffect(() => {
    const el = containerRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [logs]);

  const onScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
  };

  return (
    <div
      id="logs-panel"
      className="flex flex-col bg-bg-secondary rounded-lg ring-1 ring-inset ring-border overflow-hidden flex-1 min-h-50"
    >
      <div
        role="button"
        tabIndex={0}
        onClick={() => setPrefs({ sidePanelExpanded: !sidePanelExpanded })}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setPrefs({ sidePanelExpanded: !sidePanelExpanded });
          }
        }}
        className="flex items-center justify-between px-3 py-2 border-b border-border transition-colors shrink-0 rounded-t-lg hover:bg-bg-hover cursor-pointer focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/50 outline-none"
        title={sidePanelExpanded ? '折叠上方面板，放大日志' : '展开上方面板'}
      >
        <span className="text-sm font-medium text-text-primary">运行日志</span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setShowFilter((v) => !v);
            }}
            className={clsx(
              'p-1 rounded-md transition-colors',
              showFilter || logLevel !== 'ALL' || logQuery
                ? 'text-accent bg-accent-light'
                : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary',
            )}
            title="过滤"
          >
            <Filter className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              clearLogs();
            }}
            className="p-1 rounded-md transition-colors text-text-secondary hover:bg-bg-tertiary hover:text-text-primary"
            title="清空显示（不删日志文件）"
          >
            <Eraser className="w-3.5 h-3.5" />
          </button>
          <span className={clsx('p-0.5 rounded transition-colors', !sidePanelExpanded ? 'text-accent bg-accent-light' : 'text-text-muted')}>
            <ChevronDown
              className={clsx('w-4 h-4 transition-transform duration-150 ease-out', sidePanelExpanded && 'rotate-180')}
            />
          </span>
        </div>
      </div>

      {showFilter && (
        <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-border bg-bg-primary shrink-0">
          <div className="flex gap-1">
            {LEVELS.map((l) => (
              <button
                key={l.value}
                type="button"
                onClick={() => setLogFilter(l.value, logQuery)}
                className={clsx(
                  'px-2 py-0.5 text-xs rounded-md transition-colors',
                  logLevel === l.value ? 'bg-accent text-white' : 'bg-bg-tertiary text-text-secondary hover:bg-bg-hover',
                )}
              >
                {l.label}
              </button>
            ))}
          </div>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') setLogFilter(logLevel, query.trim());
            }}
            onBlur={() => setLogFilter(logLevel, query.trim())}
            placeholder="关键字，回车过滤"
            className="flex-1 min-w-0 px-2 py-0.5 text-xs rounded-md border border-border bg-bg-secondary text-text-primary focus:outline-none focus:border-accent"
          />
        </div>
      )}

      <div
        ref={containerRef}
        onScroll={onScroll}
        className="flex-1 min-h-0 overflow-y-auto p-2.5 font-mono text-[12px] leading-4 bg-bg-tertiary dark:bg-bg-secondary"
      >
        {logs.length === 0 ? (
          <div className="h-full flex items-center justify-center text-text-muted">暂无日志</div>
        ) : (
          logs.map((log, i) => (
            <Fragment key={log.id}>
              <div className={clsx('py-1.5 px-2 rounded-md flex items-start gap-3', levelColor(log.level))}>
                <span className="text-text-muted/90 w-[60px] flex-shrink-0 tabular-nums text-[11px] leading-4">{log.time}</span>
                <span className="min-w-0 flex-1 break-words whitespace-pre-wrap leading-4">
                  {log.level !== 'INFO' && <span className="font-semibold mr-1">{log.level}</span>}
                  {log.message}
                </span>
              </div>
              {i < logs.length - 1 && <div className="mx-4 my-1 h-px bg-border/50" aria-hidden />}
            </Fragment>
          ))
        )}
      </div>
    </div>
  );
}
