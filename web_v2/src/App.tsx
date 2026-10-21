import { useCallback, useEffect, useRef, useState } from 'react';
import clsx from 'clsx';
import { AlertCircle, Loader2 } from 'lucide-react';
import { useStore } from '@/store';
import { TitleBar } from './components/TitleBar';
import { TopBar } from './components/TopBar';
import { TaskList } from './components/TaskList';
import { Toolbar } from './components/Toolbar';
import { PresetPanel } from './components/PresetPanel';
import { AddComponentPanel } from './components/AddComponentPanel';
import { StatusPanel } from './components/StatusPanel';
import { ScreenshotPanel } from './components/ScreenshotPanel';
import { LogsPanel } from './components/LogsPanel';
import { SettingsPage } from './components/SettingsPage';

const MIN_LEFT = 420;
const MIN_RIGHT = 260;

export default function App() {
  const ready = useStore((s) => s.ready);
  const connectionError = useStore((s) => s.connectionError);
  const page = useStore((s) => s.page);
  const init = useStore((s) => s.init);
  const prefs = useStore((s) => s.prefs);
  const setPrefs = useStore((s) => s.setPrefs);
  const [settingsExiting, setSettingsExiting] = useState(false);
  const [showSettings, setShowSettings] = useState(page === 'settings');
  const dragRef = useRef<{ startX: number; startW: number } | null>(null);

  useEffect(() => {
    void init();
  }, [init]);

  useEffect(() => {
    if (page === 'settings') {
      setShowSettings(true);
      setSettingsExiting(false);
    } else if (showSettings) {
      setSettingsExiting(true);
      const t = window.setTimeout(() => {
        setShowSettings(false);
        setSettingsExiting(false);
      }, 120);
      return () => window.clearTimeout(t);
    }
  }, [page, showSettings]);

  const onResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragRef.current = { startX: e.clientX, startW: prefs.rightPanelWidth };
      const onMove = (ev: MouseEvent) => {
        if (!dragRef.current) return;
        const delta = dragRef.current.startX - ev.clientX;
        const max = window.innerWidth - MIN_LEFT;
        const w = Math.max(MIN_RIGHT, Math.min(max, dragRef.current.startW + delta));
        setPrefs({ rightPanelWidth: w });
      };
      const onUp = () => {
        dragRef.current = null;
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },
    [prefs.rightPanelWidth, setPrefs],
  );

  return (
    <div className="h-full flex flex-col bg-bg-primary relative">
      <TitleBar />
      <TopBar />

      {!ready && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-text-muted">
          {connectionError ? (
            <>
              <AlertCircle className="w-10 h-10 text-error opacity-80" />
              <div className="text-sm text-text-secondary">连不上后端：{connectionError}</div>
              <div className="text-xs">3 秒后自动重试。确认 app_v2.py / serve_web_v2.py 在跑。</div>
            </>
          ) : (
            <>
              <Loader2 className="w-8 h-8 animate-spin text-accent" />
              <div className="text-sm">正在连接后端…</div>
            </>
          )}
        </div>
      )}

      {ready && showSettings && (
        <div className={clsx('flex-1 flex min-h-0', settingsExiting ? 'page-slide-right-exit' : 'page-slide-right-enter')}>
          <SettingsPage />
        </div>
      )}

      {ready && !showSettings && (
        <div className="flex-1 flex overflow-hidden">
          <div className="flex-1 flex flex-col border-r border-border" style={{ minWidth: MIN_LEFT }}>
            <TaskList />
            <div
              className="grid transition-[grid-template-rows] duration-150 ease-out"
              style={{ gridTemplateRows: prefs.showPresetPanel ? '1fr' : '0fr' }}
            >
              <div className="overflow-hidden min-h-0">
                <PresetPanel />
              </div>
            </div>
            <div
              className="grid transition-[grid-template-rows] duration-150 ease-out"
              style={{ gridTemplateRows: prefs.showAddPanel ? '1fr' : '0fr' }}
            >
              <div className="overflow-hidden min-h-0">
                <AddComponentPanel />
              </div>
            </div>
            <Toolbar />
          </div>

          <div
            className="w-1 hover:bg-accent/50 cursor-col-resize flex items-center justify-center group shrink-0 transition-all select-none bg-transparent"
            onMouseDown={onResizeStart}
            title="拖动调整宽度"
          >
            <div className="w-[2px] h-8 rounded-full transition-colors bg-border group-hover:bg-accent" />
          </div>

          <div
            className={clsx(
              'flex flex-col p-3 bg-bg-primary overflow-x-hidden',
              prefs.sidePanelExpanded ? 'gap-3 overflow-y-auto' : 'overflow-hidden',
            )}
            style={{ width: prefs.rightPanelWidth, minWidth: MIN_RIGHT, flexShrink: 1 }}
          >
            <div
              className="grid transition-[grid-template-rows] duration-150 ease-out"
              style={{ gridTemplateRows: prefs.sidePanelExpanded ? '1fr' : '0fr' }}
            >
              <div className="overflow-hidden min-h-0 flex flex-col gap-3">
                <StatusPanel />
                <ScreenshotPanel />
              </div>
            </div>
            <LogsPanel />
          </div>
        </div>
      )}
    </div>
  );
}
