/** 实时截图卡片（沿用 MXU ScreenshotPanel）。 */
import { useState } from 'react';
import clsx from 'clsx';
import { Camera, ChevronDown, Maximize2, Monitor, Pause, Play, X } from 'lucide-react';
import { useStore } from '@/store';

export function ScreenshotPanel() {
  const expanded = useStore((s) => s.prefs.screenshotExpanded);
  const setPrefs = useStore((s) => s.setPrefs);
  const url = useStore((s) => s.screenshotUrl);
  const error = useStore((s) => s.screenshotError);
  const streaming = useStore((s) => s.streaming);
  const setStreaming = useStore((s) => s.setStreaming);
  const captureOnce = useStore((s) => s.captureOnce);
  const [fullscreen, setFullscreen] = useState(false);

  const iconBtn = (disabled: boolean, active = false) =>
    clsx(
      'p-1 rounded-md transition-colors',
      disabled
        ? 'text-text-muted cursor-not-allowed'
        : active
          ? 'text-success hover:bg-bg-tertiary'
          : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary',
    );

  return (
    <div className="bg-bg-secondary rounded-lg ring-1 ring-inset ring-border overflow-hidden shrink-0">
      <div
        role="button"
        tabIndex={0}
        onClick={() => setPrefs({ screenshotExpanded: !expanded })}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setPrefs({ screenshotExpanded: !expanded });
          }
        }}
        className={clsx(
          'w-full flex items-center justify-between px-3 py-2 hover:bg-bg-hover cursor-pointer focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/50 outline-none',
          expanded ? 'rounded-t-lg' : 'rounded-lg',
        )}
      >
        <div className="flex items-center gap-2">
          <Monitor className="w-4 h-4 text-text-secondary" />
          <span className="text-sm font-medium text-text-primary">游戏画面</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              void captureOnce();
            }}
            className={iconBtn(false)}
            title="抓一帧"
          >
            <Camera className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setStreaming(!streaming);
            }}
            className={iconBtn(false, streaming)}
            title={streaming ? '停止自动刷新' : '每 3 秒自动抓帧'}
          >
            {streaming ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              if (url) setFullscreen(true);
            }}
            disabled={!url}
            className={iconBtn(!url)}
            title="放大"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
          <ChevronDown
            className={clsx('w-4 h-4 text-text-muted transition-transform duration-150 ease-out', expanded && 'rotate-180')}
          />
        </div>
      </div>

      <div
        className="grid transition-[grid-template-rows] duration-150 ease-out"
        style={{ gridTemplateRows: expanded ? '1fr' : '0fr' }}
      >
        <div className="overflow-hidden min-h-0">
          <div className="border-t border-border" />
          <div className="p-3">
            <div className="aspect-video bg-bg-tertiary rounded-md flex items-center justify-center overflow-hidden relative">
              {url ? (
                <>
                  <img src={url} alt="Screenshot" className="w-full h-full object-contain rounded-md" />
                  {streaming && (
                    <div className="absolute top-2 right-2 flex items-center gap-1 px-1.5 py-0.5 bg-success/80 rounded text-white text-xs">
                      <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse" />
                      LIVE
                    </div>
                  )}
                </>
              ) : (
                <div className="flex flex-col items-center gap-2 text-text-muted">
                  <Monitor className="w-10 h-10 opacity-30" />
                  {error ? (
                    <span className="text-xs text-error">{error}</span>
                  ) : (
                    <span className="text-xs">还没有截图，点上面的相机抓一帧</span>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {fullscreen && url && (
        <div
          className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-8"
          onClick={() => setFullscreen(false)}
        >
          <div
            className="relative bg-bg-secondary rounded-xl border border-border shadow-2xl max-w-[90vw] max-h-[90vh] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-bg-tertiary/50">
              <div className="flex items-center gap-2">
                <Monitor className="w-4 h-4 text-text-secondary" />
                <span className="text-sm font-medium text-text-primary">游戏画面</span>
              </div>
              <button
                type="button"
                onClick={() => setFullscreen(false)}
                className="p-1.5 rounded-md hover:bg-bg-hover text-text-secondary hover:text-text-primary transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 bg-bg-primary flex items-center justify-center overflow-auto">
              <img src={url} alt="Screenshot" className="max-w-full max-h-[75vh] object-contain rounded-md" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
