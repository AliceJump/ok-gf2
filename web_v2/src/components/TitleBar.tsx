/**
 * 自绘标题栏：只在 pywebview 无边框窗口里显示（URL 带 ?frameless=1），
 * 浏览器里不渲染。窗口按钮通过 pywebview 的 js_api 调回 Python。
 */
import { Copy, Minus, Square, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useStore } from '@/store';

interface PyWebviewApi {
  minimize: () => Promise<void>;
  toggle_maximize: () => Promise<boolean>;
  close: () => Promise<void>;
}

declare global {
  interface Window {
    pywebview?: { api: PyWebviewApi };
  }
}

export function isFrameless(): boolean {
  return new URLSearchParams(location.search).get('frameless') === '1';
}

export function TitleBar() {
  const title = useStore((s) => s.title);
  const [maximized, setMaximized] = useState(false);
  const [ready, setReady] = useState(!!window.pywebview);

  useEffect(() => {
    if (ready) return;
    const onReady = () => setReady(true);
    window.addEventListener('pywebviewready', onReady);
    return () => window.removeEventListener('pywebviewready', onReady);
  }, [ready]);

  if (!isFrameless()) return null;
  const api = window.pywebview?.api;
  const btn = 'w-12 h-full flex items-center justify-center text-text-secondary hover:bg-bg-hover transition-colors';

  return (
    <div className="pywebview-drag-region h-8 flex items-center justify-between bg-bg-secondary border-b border-border select-none shrink-0">
      <div className="flex items-center h-full pywebview-drag-region">
        <div className="w-8 h-8 flex items-center justify-center">
          <img src="/v2/icon.png" alt="" className="w-4 h-4" onError={(e) => ((e.target as HTMLImageElement).style.display = 'none')} />
        </div>
        <span className="text-xs text-text-secondary px-2 truncate max-w-lg">{title}</span>
      </div>
      <div className="flex h-full" style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}>
        <button type="button" onClick={() => api?.minimize()} className={btn} title="最小化" disabled={!api}>
          <Minus className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={async () => {
            if (!api) return;
            setMaximized(await api.toggle_maximize());
          }}
          className={btn}
          title={maximized ? '还原' : '最大化'}
          disabled={!api}
        >
          {maximized ? <Copy className="w-3.5 h-3.5 rotate-180" /> : <Square className="w-3 h-3" />}
        </button>
        <button
          type="button"
          onClick={() => api?.close()}
          className="w-12 h-full flex items-center justify-center text-text-secondary hover:bg-red-500 hover:text-white transition-colors"
          title="关闭"
          disabled={!api}
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
