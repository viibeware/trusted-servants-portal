// Footer builder — inline, page-builder-style structure editor for the
// Footer admin. Replaces the old "open a separate layout-builder modal"
// flow: the admin arranges footer blocks into rows/columns right on the
// page (drag to reorder/move, palette to add, × to remove, click a block
// to edit its content in the existing modal), and a sticky save bar
// commits everything.
//
// Arrangement is serialised into the hidden #footer-layout-json input as
// rows: [{cols, columns: [[{type}], ...]}] — the exact shape the footer
// CustomLayout + public _custom.html render already consume. Block
// CONTENT stays in the existing per-type modals (saved via parse_footer);
// this file only owns the LAYOUT (which blocks, where).
(function () {
  const rowsEl = document.querySelector('[data-footer-rows]');
  const hidden = document.getElementById('footer-layout-json');
  const form = document.getElementById('footer-form');
  if (!rowsEl || !hidden || !form) return;
  if (typeof Sortable === 'undefined') {
    console.warn('[footer_builder] Sortable not loaded — drag-drop disabled');
  }

  // ── Pill / row factories (clone from server-rendered <template>s so
  //    fresh blocks carry the right icon SVG + label without building
  //    markup in JS). ──────────────────────────────────────────────
  function pillTemplate(type) {
    const t = document.querySelector('[data-footer-pill-tpl="' + type + '"]');
    return t ? t.content.firstElementChild.cloneNode(true) : null;
  }

  function colEl(col) {
    const wrap = document.createElement('div');
    wrap.className = 'fe-page-structure-col';
    const list = document.createElement('div');
    list.className = 'fe-page-structure-block-list';
    list.setAttribute('data-footer-col', '');
    wrap.appendChild(list);
    (col || []).forEach(function (b) {
      const p = pillTemplate(b.type || (b.get && b.get('type')));
      if (p) list.appendChild(p);
    });
    return wrap;
  }

  function rowEl(cols, columns) {
    cols = Math.max(1, Math.min(4, cols || 1));
    const row = document.createElement('div');
    row.className = 'fe-page-structure-row fe-page-structure-row--split';
    row.setAttribute('data-footer-row', '');
    row.dataset.cols = cols;
    const label = document.createElement('div');
    label.className = 'fe-page-structure-row-label';
    label.innerHTML = '<span class="fe-page-structure-row-num">Row</span>'
      + '<span class="muted smaller">' + cols + ' column' + (cols === 1 ? '' : 's') + '</span>';
    const rm = document.createElement('button');
    rm.type = 'button';
    rm.className = 'btn btn-sm fe-page-structure-row-action fe-page-structure-row-remove';
    rm.setAttribute('data-footer-row-remove', '');
    rm.textContent = '× Remove row';
    label.appendChild(rm);
    const colsWrap = document.createElement('div');
    colsWrap.className = 'fe-page-structure-cols fe-page-structure-cols--' + cols;
    for (let i = 0; i < cols; i++) {
      colsWrap.appendChild(colEl((columns && columns[i]) || []));
    }
    row.appendChild(label);
    row.appendChild(colsWrap);
    return row;
  }

  // ── Sortable wiring ────────────────────────────────────────────────
  function makeSortable(list) {
    if (typeof Sortable === 'undefined' || list._sortable) return;
    list._sortable = new Sortable(list, {
      group: 'footer-blocks', animation: 140, ghostClass: 'is-drag-ghost',
      draggable: '.fe-page-structure-block',
      onSort: sync, onAdd: sync, onRemove: sync,
    });
  }
  function wireAllSortables() {
    rowsEl.querySelectorAll('[data-footer-col]').forEach(makeSortable);
  }

  // ── Serialise arrangement → hidden field ───────────────────────────
  function sync() {
    const rows = [];
    rowsEl.querySelectorAll('[data-footer-row]').forEach(function (row) {
      const columns = [];
      row.querySelectorAll('[data-footer-col]').forEach(function (col) {
        const blocks = [];
        col.querySelectorAll('.fe-page-structure-block[data-type]').forEach(function (p) {
          blocks.push({ type: p.dataset.type });
        });
        columns.push(blocks);
      });
      // Drop fully-empty rows from the saved arrangement.
      if (columns.some(function (c) { return c.length; })) {
        rows.push({ type: 'row', cols: columns.length, columns: columns });
      }
    });
    hidden.value = JSON.stringify(rows);
    markDirty();
    refreshEmptyState();
  }

  function refreshEmptyState() {
    const has = rowsEl.querySelector('.fe-page-structure-block[data-type]');
    const empty = document.querySelector('[data-footer-empty]');
    if (empty) empty.hidden = !!has;
  }

  // ── Sticky save bar ────────────────────────────────────────────────
  const saveBar = document.getElementById('footer-save-bar');
  let dirty = false;
  function markDirty() {
    if (dirty) return;
    dirty = true;
    if (saveBar) saveBar.hidden = false;
  }
  // Any content-modal field change also makes the footer dirty.
  form.addEventListener('input', markDirty);
  form.addEventListener('change', markDirty);

  // ── Palette: click a tile to add that block to the last row's first
  //    column (creating a 1-column row if none exists). ───────────────
  document.addEventListener('click', function (e) {
    const tile = e.target.closest('[data-footer-palette-tile]');
    if (tile) {
      e.preventDefault();
      const type = tile.dataset.type;
      const pill = pillTemplate(type);
      if (!pill) return;
      let lastCol = rowsEl.querySelector('[data-footer-row]:last-child [data-footer-col]');
      if (!lastCol) {
        const r = rowEl(1, [[]]);
        rowsEl.appendChild(r);
        makeSortable(r.querySelector('[data-footer-col]'));
        lastCol = r.querySelector('[data-footer-col]');
      }
      lastCol.appendChild(pill);
      sync();
      return;
    }
    // Add a row (1–4 columns).
    const addRow = e.target.closest('[data-footer-add-row]');
    if (addRow) {
      e.preventDefault();
      const cols = parseInt(addRow.dataset.cols || '1', 10);
      const r = rowEl(cols, []);
      rowsEl.appendChild(r);
      r.querySelectorAll('[data-footer-col]').forEach(makeSortable);
      sync();
      return;
    }
    // Remove a block.
    const rm = e.target.closest('[data-footer-remove]');
    if (rm) {
      e.preventDefault();
      const block = rm.closest('.fe-page-structure-block');
      if (block) block.remove();
      sync();
      return;
    }
    // Remove a row.
    const rmRow = e.target.closest('[data-footer-row-remove]');
    if (rmRow) {
      e.preventDefault();
      const row = rmRow.closest('[data-footer-row]');
      if (row && confirm('Remove this row? Blocks in it are removed from the layout (their saved content is kept and can be re-added).')) {
        row.remove();
        sync();
      }
      return;
    }
    // Click a block (not its remove button) → open its content modal.
    const pill = e.target.closest('.fe-page-structure-block[data-open-modal]');
    if (pill && !e.target.closest('[data-footer-remove]')) {
      const id = pill.getAttribute('data-open-modal');
      const m = document.getElementById(id);
      if (m) {
        m.classList.add('open');
        m.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
      }
    }
  });

  wireAllSortables();
  refreshEmptyState();
})();
