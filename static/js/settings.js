// settings.js — user drawing preferences: length unit (display), sketch grid
// size, and snap increment. mm stays the WORKING unit everywhere (geometry is
// exact in mm); the unit here only changes how lengths/volumes are DISPLAYED.
// Persisted in localStorage; broadcasts 'settings-changed' when it changes.

import { bus } from './bus.js';

const UNITS = {
  mm: { label: 'mm', f: 1,        dp: 2, vdp: 1 },
  cm: { label: 'cm', f: 0.1,      dp: 3, vdp: 3 },
  in: { label: 'in', f: 1 / 25.4, dp: 4, vdp: 4 },
};

const DEFAULTS = { unit: 'mm', gridMm: 10, snapMm: 1 };

export const SETTINGS = { ...DEFAULTS };

export function loadSettings() {
  try {
    Object.assign(SETTINGS, JSON.parse(localStorage.getItem('tcad-settings') || '{}'));
  } catch { /* ignore corrupt prefs */ }
  if (!UNITS[SETTINGS.unit]) SETTINGS.unit = 'mm';
}

function save() {
  try { localStorage.setItem('tcad-settings', JSON.stringify(SETTINGS)); }
  catch { /* private mode: keep in memory only */ }
  bus.emit('settings-changed', SETTINGS);
}

export function unitLabel() { return UNITS[SETTINGS.unit].label; }

/* a length in mm -> a string in the display unit, e.g. "40 mm" / "1.5748 in" */
export function fmtLen(mm, withUnit = true) {
  const u = UNITS[SETTINGS.unit];
  const v = round(mm * u.f, u.dp);
  return withUnit ? `${v} ${u.label}` : String(v);
}

/* a volume in mm³ -> a string in the display unit cubed */
export function fmtVol(mm3) {
  const u = UNITS[SETTINGS.unit];
  const v = round(mm3 * u.f ** 3, u.vdp);
  return `${v} ${u.label}³`;
}

/* a value typed in the DISPLAY unit -> mm (the working unit) */
export function toMm(v) { return v / UNITS[SETTINGS.unit].f; }

function round(v, dp) {
  const k = 10 ** dp;
  return Math.round(v * k) / k;
}

/* ---------------- the Settings dialog ---------------- */

const dlg = () => document.getElementById('settingsDialog');

export function openSettings() {
  document.getElementById('setUnit').value = SETTINGS.unit;
  document.getElementById('setGrid').value = SETTINGS.gridMm;
  document.getElementById('setSnap').value = SETTINGS.snapMm;
  dlg().showModal();
}

export function initSettings() {
  loadSettings();
  // explicit button handlers, not native form submit: the number inputs'
  // min/step validation silently blocks a <form method="dialog"> submit.
  document.getElementById('setCancel').onclick = () => dlg().close();
  document.getElementById('setApply').onclick = () => {
    dlg().close();
    SETTINGS.unit = document.getElementById('setUnit').value;
    SETTINGS.gridMm = Math.max(0.1, Number(document.getElementById('setGrid').value) || 10);
    SETTINGS.snapMm = Math.max(0, Number(document.getElementById('setSnap').value) || 0);
    save();
  };
}
