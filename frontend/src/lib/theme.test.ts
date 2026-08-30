/**
 * The rule this feature turns on: "system" is the absence of a choice, and only
 * the absence of a choice lets the app override anything.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  applyTheme,
  readPreference,
  resolve,
  setPreference,
  systemTheme,
  watchSystemTheme,
} from './theme';

/** A stand-in for a phone set to dark or light, with listeners that fire. */
function stubMatchMedia(prefersDark: boolean) {
  const listeners = new Set<() => void>();
  const media = {
    matches: prefersDark,
    addEventListener: (_: string, fn: () => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
  };
  vi.stubGlobal('matchMedia', () => media);
  return { fire: () => listeners.forEach((fn) => fn()), count: () => listeners.size };
}

beforeEach(() => {
  document.documentElement.removeAttribute('data-theme');
  document.documentElement.removeAttribute('data-theme-source');
  try {
    window.localStorage?.clear();
  } catch {
    /* jsdom here has no localStorage — the module is built for that. */
  }
});

afterEach(() => vi.unstubAllGlobals());

describe('appearance', () => {
  it('defaults to system when nothing was chosen', () => {
    expect(readPreference()).toBe('system');
  });

  it('resolves system to whatever the phone says', () => {
    stubMatchMedia(true);
    expect(systemTheme()).toBe('dark');
    expect(resolve('system')).toBe('dark');

    stubMatchMedia(false);
    expect(resolve('system')).toBe('light');
  });

  it('resolves an explicit choice to itself, whatever the phone says', () => {
    stubMatchMedia(true);
    expect(resolve('light')).toBe('light');
    expect(resolve('dark')).toBe('dark');
  });

  it('marks the source only when nothing was chosen', () => {
    stubMatchMedia(true);

    // This attribute is the entire on-course override: CSS uses it to tell
    // "dark because they asked" from "dark because the phone is".
    applyTheme('system');
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(document.documentElement.dataset.themeSource).toBe('system');

    applyTheme('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(document.documentElement.dataset.themeSource).toBeUndefined();
  });

  it('follows the phone while system is selected', () => {
    const media = stubMatchMedia(false);
    const onChange = vi.fn();

    const stop = watchSystemTheme(onChange);
    media.fire();
    expect(onChange).toHaveBeenCalledOnce();

    stop();
    expect(media.count()).toBe(0);
  });

  it('does not throw when the browser has no usable storage', () => {
    // jsdom here has none at all, which is the condition to survive: this runs
    // on every boot, and failing to start costs more than losing a preference.
    stubMatchMedia(false);
    expect(() => setPreference('dark')).not.toThrow();
    expect(document.documentElement.dataset.theme).toBe('dark');
  });
});
