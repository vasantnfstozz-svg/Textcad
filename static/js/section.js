// section.js — Section view (Tier 2, specs/section-view.md): Fusion's Section
// Analysis. A clipping plane cuts the bodies open ON SCREEN so the user looks
// into the part; nothing about the design changes, nothing is saved, no
// request goes to the server (the plane is three numbers the user chose).
// The viewport owns the plane and the materials (viewport.beginSection);
// this file is the panel: Axis, Offset (the display unit, like every length
// box), Flip, Close — and the arrow's value coming back into the box.
//
// A VIEW STATE, not a command (parity rule 9 is about commands): it sets no
// modal lock, so every tool still opens while the model is cut open. Esc
// closes the section only when no tool holds the lock — tool.js's Escape
// cancels an open tool first, and this handler stands down while S.modalTool
// is set.

import { S } from './state.js';
import { bus } from './bus.js';
import { beginSection, setSectionOffset, endSection, sectionInfo } from './viewport.js';
import { SETTINGS, toMm, fmtLen } from './settings.js';

const g = id => document.getElementById(id);
let on = false;
let timer = null;

const axis = () => g('scAxis').value;
const flip = () => g('scFlip').checked;
const readOffset = () => toMm(Number(g('scOffset').value) || 0);
function writeOffset(v) {
  g('scOffset').value = SETTINGS.unit === 'mm' ? Math.round(v * 100) / 100 : fmtLen(v, false);
}
/* (re)place the plane: null = the model's centre along the axis */
function place(offset) {
  const r = beginSection(axis(), offset, flip(),
    v => writeOffset(v),                       // dragging: the box follows the arrow
    v => writeOffset(v));                      // release: the plane already sits there
  writeOffset(r.offset);
  g('scStatus').textContent = `hiding the ${flip() ? 'low' : 'high'} side of ${axis()}`;
}

export function isSectionOn() { return on; }
export function openSection() {
  if (on) { place(readOffset()); return; }
  on = true;
  g('sectionDialog').style.display = 'block';
  place(null);
  bus.emit('msg', 'bot', 'Section view: the model is cut open at the gold plane — drag the ' +
    'arrow or type an offset to move it, Flip hides the other side. Close (or Esc with ' +
    'no tool open) puts the model back. Nothing in the design changes.');
}
export function closeSection() {
  if (!on) return;
  on = false;
  endSection();
  g('sectionDialog').style.display = 'none';
}
export function toggleSection() { if (on) closeSection(); else openSection(); }

export function initSection() {
  g('scAxis').onchange = () => place(null);          // a new axis starts at the centre again
  g('scFlip').onchange = () => place(readOffset());
  g('scOffset').oninput = () => {                    // typed: the plane follows after a pause
    clearTimeout(timer);
    timer = setTimeout(() => { timer = null; if (on) setSectionOffset(readOffset()); }, 150);
  };
  g('scClose').onclick = closeSection;
  // CAPTURE phase: this runs BEFORE tool.js's and measure.js's Escape
  // handlers, while the tool still holds the lock — so one Esc cancels an
  // open tool and leaves the section; the next Esc, with nothing open,
  // closes the section. (Registered after them in the bubble phase, it saw
  // the lock already released by the same key and closed both at once.)
  window.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !e.repeat && on && !S.modalTool) closeSection();
  }, true);
  // The display unit changed under an OPEN section panel. Every tool panel is
  // safe from this (Settings is a ribbon action and modalGuard refuses those
  // while a tool holds the lock), but a section takes no lock on purpose — so
  // this is the one box whose number has to be rewritten under the user's
  // hands. The millimetres are the VIEWPORT's (it owns the plane), never the
  // box's: re-reading the box under the new unit left the number alone and
  // silently multiplied what it meant — measured, a plane at 4 mm read as
  // 4 in and the next click (Flip) moved it to 101.6 mm.
  bus.on('settings-changed', () => { if (on) writeOffset(sectionInfo().offset); });
}
