// splitters.js — draggable dividers between the three panes (feature tree |
// viewport | AI designer). Drag to resize, double-click to reset. Sizes are
// remembered in localStorage. The viewport re-fits itself automatically via
// its ResizeObserver.

const LIMITS = { tree: [180, 640], chat: [220, 640] };
const DEFAULTS = { tree: 320, chat: 330 };

function apply(pane, key, px) {
  const [min, max] = LIMITS[key];
  px = Math.max(min, Math.min(max, px));
  pane.style.width = px + 'px';
  pane.style.minWidth = px + 'px';   // beat the CSS min-width
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
