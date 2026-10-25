/** 通用表单控件（沿用 MXU FormControls 的样式） */
import clsx from 'clsx';

interface SwitchButtonProps {
  value: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
  tabIndex?: number;
}

export function SwitchButton({ value, onChange, disabled, tabIndex }: SwitchButtonProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      onClick={() => !disabled && onChange(!value)}
      disabled={disabled}
      tabIndex={tabIndex}
      className={clsx(
        'relative w-11 h-6 rounded-full transition-colors flex-shrink-0',
        value ? 'bg-accent' : 'bg-bg-active',
        disabled && 'cursor-not-allowed opacity-60',
      )}
    >
      <span
        className={clsx(
          'absolute top-1 left-1 w-4 h-4 rounded-full bg-white shadow-sm transition-transform duration-200',
          value ? 'translate-x-5' : 'translate-x-0',
        )}
      />
    </button>
  );
}

interface TextInputProps {
  value: string;
  onChange: (value: string) => void;
  onCommit?: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  hasError?: boolean;
  className?: string;
  type?: 'text' | 'number' | 'password';
}

export function TextInput({
  value,
  onChange,
  onCommit,
  placeholder,
  disabled,
  hasError,
  className,
  type = 'text',
}: TextInputProps) {
  return (
    <input
      type={type}
      autoComplete={type === 'password' ? 'off' : undefined}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onBlur={(e) => onCommit?.(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
      }}
      placeholder={placeholder}
      disabled={disabled}
      className={clsx(
        'px-3 py-1.5 text-sm rounded-md border',
        'bg-bg-secondary text-text-primary',
        'focus:outline-none focus:ring-1',
        disabled && 'opacity-60 cursor-not-allowed',
        hasError
          ? 'border-error focus:border-error focus:ring-error/20'
          : 'border-border focus:border-accent focus:ring-accent/20',
        className,
      )}
    />
  );
}

interface NumberInputProps {
  value: number | '';
  onChange: (value: number | '') => void;
  onCommit?: (value: number | '') => void;
  min?: number | null;
  max?: number | null;
  step?: number | 'any';
  disabled?: boolean;
  className?: string;
}

export function NumberInput({
  value,
  onChange,
  onCommit,
  min,
  max,
  step = 1,
  disabled,
  className,
}: NumberInputProps) {
  const parse = (raw: string): number | '' => {
    if (raw === '' || raw === '-') return '';
    const v = parseFloat(raw);
    return Number.isNaN(v) ? '' : v;
  };
  return (
    <input
      type="number"
      min={min ?? undefined}
      max={max ?? undefined}
      step={step}
      value={value}
      onChange={(e) => onChange(parse(e.target.value))}
      onBlur={(e) => onCommit?.(parse(e.target.value))}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
      }}
      disabled={disabled}
      className={clsx(
        'w-28 px-3 py-1.5 text-sm rounded-md border',
        'bg-bg-secondary text-text-primary border-border',
        'focus:outline-none focus:ring-1 focus:ring-accent/20 focus:border-accent',
        disabled && 'opacity-60 cursor-not-allowed',
        className,
      )}
    />
  );
}

interface TextAreaProps {
  value: string;
  onChange: (value: string) => void;
  onCommit?: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  rows?: number;
}

export function TextArea({
  value,
  onChange,
  onCommit,
  placeholder,
  disabled,
  className,
  rows = 3,
}: TextAreaProps) {
  return (
    <textarea
      value={value}
      rows={rows}
      onChange={(e) => onChange(e.target.value)}
      onBlur={(e) => onCommit?.(e.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      className={clsx(
        'px-3 py-1.5 text-sm rounded-md border resize-y',
        'bg-bg-secondary text-text-primary border-border',
        'focus:outline-none focus:ring-1 focus:ring-accent/20 focus:border-accent',
        disabled && 'opacity-60 cursor-not-allowed',
        className,
      )}
    />
  );
}
