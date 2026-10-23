import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown } from 'lucide-react';
import clsx from 'clsx';

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  className?: string;
}

interface Pos {
  top?: number;
  bottom?: number;
  left: number;
  width: number;
  maxHeight: number;
}

/** 自绘下拉框（沿用 MXU OptionSelectDropdown 的样式，通过 Portal 脱离父容器裁切） */
export function Select({ value, options, onChange, disabled, className }: SelectProps) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<Pos | null>(null);
  const [active, setActive] = useState(-1);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();
  const selected = options.find((o) => o.value === value);
  const isDisabled = disabled || options.length === 0;

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const below = window.innerHeight - rect.bottom - 8;
    const above = rect.top - 8;
    const wanted = Math.min(320, options.length * 36 + 8);
    if (below >= wanted || below >= above) {
      setPos({ top: rect.bottom + 4, left: rect.left, width: rect.width, maxHeight: Math.min(wanted, below) });
    } else {
      setPos({
        bottom: window.innerHeight - rect.top + 4,
        left: rect.left,
        width: rect.width,
        maxHeight: Math.min(wanted, above),
      });
    }
    setActive(options.findIndex((o) => o.value === value));
  }, [open, options, value]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t) || listRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onScroll = () => setOpen(false);
    document.addEventListener('mousedown', close);
    window.addEventListener('resize', onScroll);
    document.addEventListener('scroll', onScroll, true);
    return () => {
      document.removeEventListener('mousedown', close);
      window.removeEventListener('resize', onScroll);
      document.removeEventListener('scroll', onScroll, true);
    };
  }, [open]);

  const commit = (v: string) => {
    onChange(v);
    setOpen(false);
    triggerRef.current?.focus();
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (isDisabled) return;
    if (!open && (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      setOpen(true);
      return;
    }
    if (!open) return;
    if (e.key === 'Escape') setOpen(false);
    else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((i) => Math.min(options.length - 1, i + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault();
      commit(options[active].value);
    }
  };

  return (
    <div className={clsx('relative', className)}>
      <button
        type="button"
        ref={triggerRef}
        disabled={isDisabled}
        onClick={() => !isDisabled && setOpen((o) => !o)}
        onKeyDown={onKey}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        className={clsx(
          'w-full px-3 py-1.5 text-sm rounded-md border flex items-center justify-between gap-2',
          'bg-bg-secondary text-text-primary border-border',
          'focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20',
          isDisabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer hover:bg-bg-hover transition-colors',
        )}
      >
        <span className="truncate">{selected?.label ?? value}</span>
        <ChevronDown
          className={clsx('w-4 h-4 text-text-secondary transition-transform shrink-0', open && 'rotate-180')}
        />
      </button>
      {open &&
        pos &&
        createPortal(
          <div
            id={listboxId}
            ref={listRef}
            role="listbox"
            className="fixed z-[9999] overflow-y-auto rounded-lg border border-border bg-bg-primary shadow-xl outline-none animate-in"
            style={{ top: pos.top, bottom: pos.bottom, left: pos.left, width: pos.width, maxHeight: pos.maxHeight }}
          >
            {options.map((opt, i) => {
              const isSelected = opt.value === value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  onClick={() => commit(opt.value)}
                  onMouseEnter={() => setActive(i)}
                  className={clsx(
                    'w-full px-3 py-2 text-left text-sm flex items-center justify-between gap-2',
                    i === active
                      ? 'bg-bg-active text-text-primary'
                      : isSelected
                        ? 'bg-accent/10 text-accent'
                        : 'text-text-primary hover:bg-bg-hover',
                  )}
                >
                  <span className="truncate">{opt.label}</span>
                  {isSelected && <Check className="w-4 h-4 flex-shrink-0" />}
                </button>
              );
            })}
          </div>,
          document.body,
        )}
    </div>
  );
}
