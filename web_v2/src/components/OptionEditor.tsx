/**
 * 按配置项的 kind 渲染一行选项，样式沿用 MXU OptionEditor：
 * boolean → 整行可点的开关；select → 右侧下拉；数字/文本 → 右侧输入框；
 * 有候选项的多选 → 四列按钮格；多行/列表 → 文本域。
 */
import { useEffect, useState } from 'react';
import clsx from 'clsx';
import type { ConfigField } from '@/api';
import { NumberInput, Select, SwitchButton, TextArea, TextInput } from './controls';

interface OptionRowProps {
  field: ConfigField;
  onChange: (value: unknown) => Promise<void> | void;
  disabled?: boolean;
  /** 是否作为子项缩进显示 */
  nested?: boolean;
}

function Label({ field }: { field: ConfigField }) {
  return (
    <div className="min-w-0">
      <div className="text-sm text-text-secondary">{field.key}</div>
      {field.description && (
        <div className="text-xs text-text-muted whitespace-pre-line mt-0.5">{field.description}</div>
      )}
    </div>
  );
}

const wrap = (nested?: boolean, extra?: string) =>
  clsx('space-y-3', nested && 'ml-4 pl-3 border-l-2 border-border', extra);

export function OptionRow({ field, onChange, disabled, nested }: OptionRowProps) {
  const kind = field.kind;

  if (kind === 'boolean') {
    const checked = !!field.value;
    const toggle = () => !disabled && onChange(!checked);
    return (
      <div className={wrap(nested)}>
        <div
          role="switch"
          aria-checked={checked}
          tabIndex={disabled ? -1 : 0}
          onClick={toggle}
          onKeyDown={(e) => {
            if (e.target !== e.currentTarget) return;
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              toggle();
            }
          }}
          className={clsx(
            'flex items-center justify-between gap-3 rounded-md px-2 py-1.5 -mx-2 transition-colors',
            disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer hover:bg-bg-hover',
          )}
        >
          <div className="min-w-0 flex-1 max-w-[70%]">
            <Label field={field} />
          </div>
          <div className="pointer-events-none flex-shrink-0" aria-hidden>
            <SwitchButton value={checked} onChange={() => undefined} disabled={disabled} tabIndex={-1} />
          </div>
        </div>
      </div>
    );
  }

  if (kind === 'select') {
    const options = (field.options ?? []).map((o) => ({ value: String(o), label: String(o) }));
    return (
      <div className={wrap(nested)}>
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1 max-w-[60%]">
            <Label field={field} />
          </div>
          <Select
            className="w-[36%] flex-shrink-0 ml-auto"
            value={String(field.value ?? '')}
            options={options}
            disabled={disabled}
            onChange={(v) => onChange(v)}
          />
        </div>
      </div>
    );
  }

  if (kind === 'integer' || kind === 'number') {
    return <NumberRow field={field} onChange={onChange} disabled={disabled} nested={nested} />;
  }

  if ((kind === 'multi_selection' || kind === 'list') && Array.isArray(field.options) && field.options.length) {
    const current = new Set((Array.isArray(field.value) ? field.value : []).map(String));
    return (
      <div className={wrap(nested)}>
        <Label field={field} />
        <div className="grid grid-cols-4 gap-1">
          {field.options.map((o) => {
            const name = String(o);
            const checked = current.has(name);
            return (
              <button
                key={name}
                type="button"
                aria-pressed={checked}
                disabled={disabled}
                title={name}
                onClick={() => {
                  const next = new Set(current);
                  if (checked) next.delete(name);
                  else next.add(name);
                  onChange([...next]);
                }}
                className={clsx(
                  'px-2 py-1.5 text-xs rounded border transition-colors min-w-0 truncate',
                  checked
                    ? 'bg-accent text-white border-accent'
                    : 'bg-bg-primary text-text-secondary border-border hover:border-accent hover:text-accent',
                  disabled && 'opacity-60 cursor-not-allowed',
                )}
              >
                {name}
              </button>
            );
          })}
        </div>
        <div className="text-xs text-text-muted">已选 {current.size} 项</div>
      </div>
    );
  }

  if (kind === 'multi_selection' || kind === 'list' || kind === 'multiline') {
    const isList = kind !== 'multiline';
    const text = isList
      ? (Array.isArray(field.value) ? field.value : []).map(String).join('\n')
      : String(field.value ?? '');
    return (
      <TextAreaRow
        field={field}
        text={text}
        hint={isList ? '每行一项' : undefined}
        disabled={disabled}
        nested={nested}
        onCommit={(v) =>
          onChange(
            isList
              ? v
                  .split('\n')
                  .map((s) => s.trim())
                  .filter(Boolean)
              : v,
          )
        }
      />
    );
  }

  // text / file / 其它：单行输入
  return <TextRow field={field} onChange={onChange} disabled={disabled} nested={nested} />;
}

function NumberRow({ field, onChange, disabled, nested }: OptionRowProps) {
  const [draft, setDraft] = useState<number | ''>(typeof field.value === 'number' ? field.value : '');
  useEffect(() => {
    setDraft(typeof field.value === 'number' ? field.value : '');
  }, [field.value]);
  return (
    <div className={wrap(nested)}>
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1 max-w-[60%]">
          <Label field={field} />
        </div>
        <div className="ml-auto flex items-center gap-2 flex-shrink-0">
          <NumberInput
            value={draft}
            onChange={setDraft}
            min={field.minimum}
            max={field.maximum}
            step={field.kind === 'number' ? 'any' : 1}
            disabled={disabled}
            onCommit={(v) => {
              if (v === '' || v === field.value) return;
              let n = field.kind === 'integer' ? Math.round(v) : v;
              if (field.minimum != null) n = Math.max(field.minimum, n);
              if (field.maximum != null) n = Math.min(field.maximum, n);
              setDraft(n);
              onChange(n);
            }}
          />
          {(field.minimum != null || field.maximum != null) && (
            <span className="text-xs text-text-muted whitespace-nowrap">
              {field.minimum ?? ''}~{field.maximum ?? ''}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function TextRow({ field, onChange, disabled, nested }: OptionRowProps) {
  const [draft, setDraft] = useState(String(field.value ?? ''));
  useEffect(() => {
    setDraft(String(field.value ?? ''));
  }, [field.value]);
  const secret = /密码|password|token|secret/i.test(field.key);
  return (
    <div className={wrap(nested)}>
      <div className="flex flex-wrap items-center gap-3 min-w-0">
        <div className="min-w-0 flex-1 basis-[12rem]">
          <Label field={field} />
        </div>
        <TextInput
          className="min-w-[min(12rem,100%)] flex-1 basis-[36%]"
          type={secret ? 'password' : 'text'}
          value={draft}
          onChange={setDraft}
          disabled={disabled}
          onCommit={(v) => {
            if (v !== String(field.value ?? '')) onChange(v);
          }}
        />
      </div>
    </div>
  );
}

function TextAreaRow({
  field,
  text,
  hint,
  disabled,
  nested,
  onCommit,
}: {
  field: ConfigField;
  text: string;
  hint?: string;
  disabled?: boolean;
  nested?: boolean;
  onCommit: (v: string) => void;
}) {
  const [draft, setDraft] = useState(text);
  useEffect(() => setDraft(text), [text]);
  return (
    <div className={wrap(nested)}>
      <Label field={field} />
      <TextArea
        className="w-full"
        value={draft}
        onChange={setDraft}
        disabled={disabled}
        onCommit={(v) => {
          if (v !== text) onCommit(v);
        }}
      />
      {hint && <div className="text-[10px] text-text-muted">{hint}</div>}
    </div>
  );
}

/** 按 keys 顺序渲染一组字段；被联动隐藏（接口里没返回）的键自动跳过 */
export function OptionList({
  fields,
  keys,
  onChange,
  disabled,
  nestedKeys,
}: {
  fields: ConfigField[];
  keys: string[];
  onChange: (key: string, value: unknown) => Promise<void> | void;
  disabled?: boolean;
  /** 作为子项缩进的键（默认用字段自带的 sub_config） */
  nestedKeys?: Set<string>;
}) {
  const rows = keys
    .map((k) => fields.find((f) => f.key === k))
    .filter((f): f is ConfigField => !!f);
  if (!rows.length) return <div className="text-sm text-text-muted">这一项没有可调的选项。</div>;
  return (
    <div className="space-y-3">
      {rows.map((f) => (
        <OptionRow
          key={f.key}
          field={f}
          disabled={disabled}
          nested={nestedKeys ? nestedKeys.has(f.key) : !!f.sub_config}
          onChange={(v) => onChange(f.key, v)}
        />
      ))}
    </div>
  );
}
