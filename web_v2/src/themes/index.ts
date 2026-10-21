/**
 * 主题管理：Light/Dark 模式 + 强调色，沿用 MXU 的预设和变量名。
 * 选择保存在 localStorage（纯本机偏好）。
 */
import lightTheme from './presets/light.json';
import darkTheme from './presets/dark.json';
import emerald from './presets/accents/emerald.json';
import lava from './presets/accents/lava.json';
import titanium from './presets/accents/titanium.json';
import celadon from './presets/accents/celadon.json';
import rosegold from './presets/accents/rosegold.json';
import danxia from './presets/accents/danxia.json';
import deepsea from './presets/accents/deepsea.json';
import cambrian from './presets/accents/cambrian.json';
import pearl from './presets/accents/pearl.json';

export interface ModeTheme {
  name: string;
  bg: { primary: string; secondary: string; tertiary: string; hover: string; active: string };
  text: { primary: string; secondary: string; tertiary: string; muted: string };
  border: { default: string; strong: string };
  shadow: { sm: string; md: string; lg: string };
}

export interface AccentTheme {
  name: string;
  label: { 'zh-CN': string; 'en-US': string };
  default: string;
  hover: string;
  light: string;
  lightDark: string;
}

export type ThemeMode = 'light' | 'dark';
export type ThemePreference = ThemeMode | 'system';

const modeThemes: Record<ThemeMode, ModeTheme> = {
  light: lightTheme as ModeTheme,
  dark: darkTheme as ModeTheme,
};

export const accentThemes: Record<string, AccentTheme> = {
  deepsea: deepsea as AccentTheme,
  emerald: emerald as AccentTheme,
  lava: lava as AccentTheme,
  titanium: titanium as AccentTheme,
  celadon: celadon as AccentTheme,
  rosegold: rosegold as AccentTheme,
  danxia: danxia as AccentTheme,
  cambrian: cambrian as AccentTheme,
  pearl: pearl as AccentTheme,
};

const fixedSemanticColors = { warning: '#f59e0b', error: '#ef4444' };

const STORAGE_KEY = 'okgf2.theme';

export interface ThemeState {
  preference: ThemePreference;
  accent: string;
}

export function loadThemeState(): ThemeState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<ThemeState>;
      const preference =
        parsed.preference === 'light' || parsed.preference === 'dark' || parsed.preference === 'system'
          ? parsed.preference
          : 'system';
      const accent = parsed.accent && accentThemes[parsed.accent] ? parsed.accent : 'deepsea';
      return { preference, accent };
    }
  } catch {
    /* 隐私模式等情况下忽略 */
  }
  return { preference: 'system', accent: 'deepsea' };
}

export function saveThemeState(state: ThemeState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* ignore */
  }
}

export function resolveThemeMode(preference: ThemePreference): ThemeMode {
  if (preference === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return preference;
}

export function applyTheme(mode: ThemeMode, accentName: string): void {
  const m = modeThemes[mode];
  const a = accentThemes[accentName] ?? accentThemes.deepsea;
  const root = document.documentElement;
  const isDark = mode === 'dark';
  root.classList.toggle('dark', isDark);
  root.style.colorScheme = isDark ? 'dark' : 'light';

  root.style.setProperty('--color-bg-primary', m.bg.primary);
  root.style.setProperty('--color-bg-secondary', m.bg.secondary);
  root.style.setProperty('--color-bg-tertiary', m.bg.tertiary);
  root.style.setProperty('--color-bg-hover', m.bg.hover);
  root.style.setProperty('--color-bg-active', m.bg.active);

  root.style.setProperty('--color-text-primary', m.text.primary);
  root.style.setProperty('--color-text-secondary', m.text.secondary);
  root.style.setProperty('--color-text-tertiary', m.text.tertiary);
  root.style.setProperty('--color-text-muted', m.text.muted);

  root.style.setProperty('--color-border', m.border.default);
  root.style.setProperty('--color-border-strong', m.border.strong);

  root.style.setProperty('--shadow-sm', m.shadow.sm);
  root.style.setProperty('--shadow-md', m.shadow.md);
  root.style.setProperty('--shadow-lg', m.shadow.lg);

  root.style.setProperty('--color-accent', a.default);
  root.style.setProperty('--color-accent-hover', a.hover);
  root.style.setProperty('--color-accent-light', isDark ? a.lightDark : a.light);

  root.style.setProperty('--color-success', a.default);
  root.style.setProperty('--color-info', a.default);
  root.style.setProperty('--color-warning', fixedSemanticColors.warning);
  root.style.setProperty('--color-error', fixedSemanticColors.error);
}

export function accentList(): { name: string; label: string; color: string }[] {
  return Object.values(accentThemes).map((a) => ({
    name: a.name,
    label: a.label['zh-CN'],
    color: a.default,
  }));
}
