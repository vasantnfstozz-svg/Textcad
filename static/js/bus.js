// bus.js — a tiny event bus so modules can talk without importing each other.
// Events used: 'doc-updated' (doc), 'msg' (who, text), 'sketch-on-face' (info).

const handlers = {};

export const bus = {
  on(event, fn) { (handlers[event] ??= []).push(fn); },
  emit(event, ...args) { for (const fn of handlers[event] || []) fn(...args); },
};
