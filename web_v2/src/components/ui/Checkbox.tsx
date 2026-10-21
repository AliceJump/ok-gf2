import type { MouseEvent } from 'react';
import { Check } from 'lucide-react';
import clsx from 'clsx';

interface CheckboxProps {
  checked: boolean;
  disabled?: boolean;
  title?: string;
  onClick: () => void;
  onContextMenu?: (e: MouseEvent) => void;
}

/** 任务卡片上的启用复选框（MXU TriStateCheckbox 的两态版） */
export function Checkbox({ checked, disabled, title, onClick, onContextMenu }: CheckboxProps) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      disabled={disabled}
      title={title}
      onClick={(e) => {
        e.stopPropagation();
        if (!disabled) onClick();
      }}
      onContextMenu={onContextMenu}
      className={clsx(
        'w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 transition-colors',
        disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
        checked
          ? 'border-accent bg-accent text-white'
          : 'border-border-strong bg-bg-primary hover:border-accent/60',
      )}
    >
      {checked && <Check className="w-3 h-3" strokeWidth={3} />}
    </button>
  );
}
