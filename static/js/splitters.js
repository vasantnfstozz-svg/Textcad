// splitters.js — the geometry of `main`: the draggable dividers between the
// three panes (feature tree | viewport | AI designer) and the tool-panel
// column between the viewport and the chat. Drag to resize, double-click to
// reset. Sizes are remembered in localStorage. The viewport re-fits itself
// automatically via its ResizeObserver.

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

/* ---------------- the tool-panel column ----------------
   Every tool panel lives in #panelCol and they STACK inside it, so the row's
   floor is the same whether one panel is open or three (a column each cost
   210 px apiece: 1000 / 1210 / 1420 px, and at 1024 with two open the AI
   designer was entirely off the screen).

   Nothing else has to know the column exists. The panels are shown and hidden
   by four different modules (tool.js, measure.js, section.js, params.js) and
   more tools will be built, so this WALKS the column after every change
   instead of keeping a list — the same reason the units guard walks the page.
   A MutationObserver callback is a microtask, so the class lands before the
   browser paints and there is no flash of an empty column. */
function syncPanelColumn(col, shown) {
  const vis = [...col.children].filter(p => p.style.display !== 'none');
  col.classList.toggle('open', vis.length > 0);
  // Parameters is a table and asks for a wider column while it is on screen
  col.classList.toggle('wide', vis.some(p => p.id === 'paramsDialog'));
  for (const p of col.children) p.classList.toggle('stacked', vis.indexOf(p) > 0);
  // A panel that opens BELOW one already open must not open out of sight: the
  // whole point of the dock is that a click is never answered somewhere the
  // user cannot see. `nearest` moves nothing when it is already visible.
  for (const p of vis) if (!shown.has(p)) p.scrollIntoView({ block: 'nearest' });
  return new Set(vis);
}

function wirePanelColumn() {
  const col = document.getElementById('panelCol');
  if (!col) return;
  let shown = new Set();
  const sync = () => { shown = syncPanelColumn(col, shown); };
  new MutationObserver(sync).observe(col, {
    attributes: true, attributeFilter: ['style'], subtree: true, childList: true });
  sync();
}

export function initSplitters() {
  wire('splitLeft', 'treePane', 'tree', true);    // drag right = wider tree
  wire('splitRight', 'chatPane', 'chat', false);  // drag right = narrower chat
  wirePanelColumn();
}
