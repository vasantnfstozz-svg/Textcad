// ask.js — the in-app replacement for window.prompt() and window.confirm().
//
// User (2026-08-26): "when i am opening a new design tab, simply a notification
// opens from a browser, ask the name, it should not be like that, i need a
// proper simple display tab where i can type file name whatever i want, and
// also it should have some default name, same for sketch tab, when nothing is
// there to sketch, i simply press cancel, and tab is opening from the browser,
// it so annoying."
//
// A native prompt() steals OS focus, cannot be styled, blocks the whole page
// (so the viewport freezes mid-render), and several browsers now dress it up
// with a scary "this site says…" banner. It also cannot offer a sensible
// default the way a real field can.
//
// Both helpers return a Promise. Cancel resolves to null / false rather than
// rejecting, so callers stay `const name = await askText(...); if (!name) return;`

const dlg = () => document.getElementById('askDialog');
const el = id => document.getElementById(id);

let closer = null;               // resolve fn for the dialog currently open

function open({ title, body = '', label = '', value = null, placeholder = '',
                ok = 'OK', cancel = 'Cancel', danger = false, hint = '',
                validate = null }) {
  const d = dlg();
  if (closer) { closer(null); closer = null; }        // never stack dialogs

  el('askTitle').textContent = title;
  el('askBody').textContent = body;
  el('askLabel').textContent = label;
  el('askOk').textContent = ok;
  el('askCancel').textContent = cancel;
  el('askOk').classList.toggle('danger', !!danger);
  el('askHint').textContent = hint;
  el('askHint').classList.remove('bad');

  const input = el('askInput');
  const wantsText = value !== null;
  input.classList.toggle('hidden', !wantsText);
  input.value = wantsText ? value : '';
  input.placeholder = placeholder;

  return new Promise(resolve => {
    let done = false;
    const finish = v => {
      if (done) return;
      done = true; closer = null;
      d.removeEventListener('close', onClose);
      resolve(v);
    };
    const onClose = () => finish(d.returnValue === 'ok'
      ? (wantsText ? input.value.trim() : true)
      : (wantsText ? null : false));

    // Guard the OK button rather than letting a bad value through: a form with
    // method="dialog" closes on submit, so validation has to happen first.
    el('askForm').onsubmit = e => {
      if (d.returnValue !== 'ok' && e.submitter && e.submitter.value !== 'ok') return;
      if (!wantsText || !validate) return;
      const bad = validate(input.value.trim());
      if (bad) {
        e.preventDefault();
        el('askHint').textContent = bad;
        el('askHint').classList.add('bad');
        input.focus();
      }
    };

    closer = finish;
    d.addEventListener('close', onClose);
    d.showModal();
    if (wantsText) { input.focus(); input.select(); }
    else el('askOk').focus();
  });
}

/** Ask for a line of text. Resolves to the trimmed string, or null if cancelled.
 *  `value` is the DEFAULT and is pre-selected, so Enter accepts it. */
export function askText(title, opts = {}) {
  return open({ title, value: opts.value ?? '', ...opts });
}

/** Ask a yes/no question. Resolves true/false. */
export function askConfirm(title, opts = {}) {
  return open({ title, value: null, ok: 'OK', ...opts });
}

/** A number field with validation built in. Resolves to a Number, or null. */
export async function askNumber(title, opts = {}) {
  const { min = null, max = null, integer = false } = opts;
  const raw = await open({
    title,
    value: String(opts.value ?? ''),
    ...opts,
    validate: v => {
      if (v === '') return 'Type a number.';
      const n = Number(v);
      if (!Number.isFinite(n)) return `"${v}" is not a number.`;
      if (integer && !Number.isInteger(n)) return 'Whole numbers only.';
      if (min !== null && n < min) return `Must be at least ${min}.`;
      if (max !== null && n > max) return `Must be at most ${max}.`;
      return null;
    },
  });
  return raw === null || raw === '' ? null : Number(raw);
}
