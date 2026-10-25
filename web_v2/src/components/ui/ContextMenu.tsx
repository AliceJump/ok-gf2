/** 右键菜单（MXU ContextMenu 的精简版：单层、portal、点外面 / Esc 关闭）。 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import clsx from 'clsx';
import type { LucideIcon } from 'lucide-react';

export interface MenuItem {
  id: string;
  label: string;
  icon?: LucideIcon;
  disabled?: boolean;
  danger?: boolean;
  divider?: boolean;
  onClick?: () => void;
}

interface Position {
  x: number;
  y: number;
}

export function useContextMenu() {
  const [state, setState] = useState<{ open: boolean; position: Position; items: MenuItem[] }>({
    open: false,
    position: { x: 0, y: 0 },
    items: [],
  });
  const showAt = useCallback((position: Position, items: MenuItem[]) => setState({ open: true, position, items }), []);
  const hide = useCallback(() => setState((s) => ({ ...s, open: false })), []);
  return { state, showAt, hide };
}

export function ContextMenu({ items, position, onClose }: { items: MenuItem[]; position: Position; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState(position);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const x = Math.min(position.x, window.innerWidth - r.width - 8);
    const y = Math.min(position.y, window.innerHeight - r.height - 8);
    setPos({ x: Math.max(8, x), y: Math.max(8, y) });
  }, [position]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  return createPortal(
    <div
      ref={ref}
      className="fixed z-[60] min-w-[160px] py-1 rounded-lg bg-bg-secondary border border-border shadow-xl animate-in"
      style={{ left: pos.x, top: pos.y }}
      onContextMenu={(e) => e.preventDefault()}
    >
      {items.map((item) =>
        item.divider ? (
          <div key={item.id} className="my-1 h-px bg-border" />
        ) : (
          <button
            key={item.id}
            type="button"
            disabled={item.disabled}
            onClick={() => {
              if (item.disabled) return;
              item.onClick?.();
              onClose();
            }}
            className={clsx(
              'w-full flex items-center gap-2 px-3 py-1.5 text-sm text-left transition-colors',
              item.disabled
                ? 'text-text-muted cursor-not-allowed'
                : item.danger
                  ? 'text-error hover:bg-error/10'
                  : 'text-text-primary hover:bg-bg-hover',
            )}
          >
            {item.icon && <item.icon className="w-4 h-4 shrink-0" />}
            <span>{item.label}</span>
          </button>
        ),
      )}
    </div>,
    document.body,
  );
}
