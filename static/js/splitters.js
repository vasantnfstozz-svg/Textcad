// splitters.js — draggable dividers between the three panes (feature tree |
// viewport | AI designer). Drag to resize, double-click to reset. Sizes are
// remembered in localStorage. The viewport re-fits itself automatically via
// its ResizeObserver.

const LIMITS = { tree: [180, 640], chat: [220, 640] };
const DEFAULTS = { tree: 320, chat: 330 };

/* The dragged width is a PREFERENCE, not a floor. This used to pin the pane
   with an inline `min-width: <dragged>px` to "beat the CSS min-width", which
   was needed when the stylesheet's floors (240 / 260) were above the limits
   here; they are 180 / 200 now, so the clamp above already keeps a drag inside
   what the CSS allows, and the pin only did harm. An inline style beats a
   stylesheet, so once `split-tree` / `split-chat` existed — one drag, or one
   double-click reset — neither pane could give way any more, and on a narrow
   window the flex row overflowed into `body { overflow: hidden }` with the AI
   designer on the far side of the edge. Measured at 1024 px with one tool
   panel open and the saved widths at their own defaults (320 / 330): the send
   button sat at 1214.7..1260, 236 px outside the window.
   Without the pin the width still wins whenever there is room for it (flex
   only shrinks an item when the row does not fit), and when there is not, the
   pane falls back to the stylesheet's floor instead of pushing the chat out. */
function apply(pane, key, px) {
  const [min, max] = LIMITS[key];
  px = Math.max(min, Math.min(max, px));
  pane.style.width = px + 'px';
  pane.style.minWidth = '';
  return px;
}

function wire(splitId, paneId, key, growsRight) {
  const split = document.getElementById(splitId);
  const pane = document.getElementById(paneId);

  const saved = Number(localStorage.getItem('split-' + key));
  if (saved) apply(pane, key, saved);

  split.addEventListener('pointerdown', e => {
    e.preventDefault();
    split.setPointerCapture(e.pointerId);
    split.classList.add('drag');
    const startX = e.clientX;
    const startW = pane.getBoundingClientRect().width;
    let latest = startW;

    const move = ev => {
      const dx = ev.clientX - startX;
      latest = apply(pane, key, growsRight ? startW + dx : startW - dx);
    };
    const up = ev => {
      split.releasePointerCapture(ev.pointerId);
      split.classList.remove('drag');
      split.removeEventListener('pointermove', move);
      split.removeEventListener('pointerup', up);
      localStorage.setItem('split-' + key, String(Math.round(latest)));
    };
    split.addEventListener('pointermove', move);
    split.addEventListener('pointerup', up);
  });

  split.addEventListener('dblclick', () => {
    apply(pane, key, DEFAULTS[key]);
    localStorage.removeItem('split-' + key);
  });
}

export function initSplitters() {
  wire('splitLeft', 'treePane', 'tree', true);    // drag right = wider tree
  wire('splitRight', 'chatPane', 'chat', false);  // drag right = narrower chat
}
