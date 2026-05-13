// SPDX-License-Identifier: AGPL-3.0-or-later
/* Per-page upcoming-events edit modal — two-way binding between the
   modal's inputs (verbatim copy of the homepage events macro markup)
   and the active Events block's data inside the page-edit form's
   blocks_json hidden input.

   Same shape as page_meetings_modal.js — see that file for the
   detailed flow notes.
*/
(function () {
  function init() {
    const modal = document.getElementById('page-events-edit-modal');
    if (!modal) return;
    const hidden = document.getElementById('page-blocks-json');
    if (!hidden) return;
    const form = document.getElementById('page-edit-form');

    let activeBlockId = null;
    const edits = new Map();

    // Range inputs → ints; the three visibility toggles + any
    // <input type="checkbox"> → bools; everything else stays a
    // string.
    const NUM_FIELDS = new Set(['max_count', 'stagger_ms']);
    const BOOL_FIELDS = new Set(['show_image', 'show_summary', 'show_location']);

    function readModal() {
      const data = {};
      modal.querySelectorAll('[data-events-field]').forEach(inp => {
        const key = inp.dataset.eventsField;
        if (!key) return;
        if (BOOL_FIELDS.has(key) || inp.type === 'checkbox') {
          data[key] = !!inp.checked;
        } else if (NUM_FIELDS.has(key) || inp.type === 'range' || inp.type === 'number') {
          const n = parseInt(inp.value, 10);
          data[key] = isNaN(n) ? 0 : n;
        } else {
          data[key] = inp.value;
        }
      });
      return data;
    }

    function readSections() {
      try { return JSON.parse(hidden.value || '[]') || []; }
      catch (_) { return []; }
    }
    function writeSections(sections) {
      hidden.value = JSON.stringify(sections);
      try { hidden.dispatchEvent(new Event('input', { bubbles: true })); } catch (_) {}
      if (form) {
        try { form.dispatchEvent(new Event('input', { bubbles: true })); } catch (_) {}
      }
      setTimeout(() => {
        const bar = document.getElementById('fe-save-bar');
        if (bar && bar.hasAttribute('hidden')) {
          bar.hidden = false;
          const m = bar.querySelector('.fe-save-bar-msg');
          if (m) m.textContent = 'Unsaved changes';
        }
      }, 50);
    }
    function walkBlocks(blocks, cb) {
      for (const b of (blocks || [])) {
        if (!b || typeof b !== 'object') continue;
        cb(b);
        if (b.type === 'container' && b.data && Array.isArray(b.data.blocks)) {
          walkBlocks(b.data.blocks, cb);
        }
      }
    }
    function findBlock(blockId) {
      const sections = readSections();
      let found = null;
      for (const sec of sections) {
        walkBlocks(sec.blocks || [], (b) => {
          if (!found && b.id === blockId) found = b;
        });
        if (found) break;
      }
      return found;
    }
    function persistModalToBlock() {
      if (!activeBlockId) return;
      const modalData = readModal();
      edits.set(activeBlockId, modalData);
      const sections = readSections();
      let touched = false;
      for (const sec of sections) {
        walkBlocks(sec.blocks || [], (b) => {
          if (b.id === activeBlockId) {
            b.data = Object.assign({}, b.data || {}, modalData);
            touched = true;
          }
        });
      }
      if (touched) writeSections(sections);
    }

    function populateModalFromBlock(block) {
      if (!block || !block.data) return;
      const data = block.data;
      modal.querySelectorAll('[data-events-field]').forEach(inp => {
        const key = inp.dataset.eventsField;
        if (!key) return;
        const v = data[key];
        if (BOOL_FIELDS.has(key) || inp.type === 'checkbox') {
          // The three visibility toggles default to TRUE if undefined
          // (mirrors the homepage's `is not defined or` Jinja guard).
          if (v == null && BOOL_FIELDS.has(key)) inp.checked = true;
          else inp.checked = !!v;
        } else if (v != null) {
          inp.value = v;
        }
      });
      modal.querySelectorAll('[data-slider-input]').forEach(inp => {
        const wrap = inp.closest('.nav-megalink-field');
        const out = wrap && wrap.querySelector('[data-slider-out]');
        if (out) out.textContent = inp.value;
      });
    }

    modal.querySelectorAll('[data-slider-input]').forEach(inp => {
      const wrap = inp.closest('.nav-megalink-field');
      const out = wrap && wrap.querySelector('[data-slider-out]');
      if (!out) return;
      inp.addEventListener('input', () => { out.textContent = inp.value; });
    });

    document.addEventListener('click', (e) => {
      const pill = e.target.closest('[data-block-type="events"][data-page-block-id]');
      if (!pill) return;
      if (e.target.closest('[data-be-remove-block]')) return;
      activeBlockId = pill.dataset.pageBlockId;
      let payload = null;
      try { payload = JSON.parse(pill.getAttribute('data-block-payload') || 'null'); }
      catch (_) {}
      if (!payload) payload = findBlock(activeBlockId);
      if (payload) populateModalFromBlock(payload);
    }, true);

    function flagDirty() {
      if (form) {
        try { form.dispatchEvent(new Event('input', { bubbles: true })); } catch (_) {}
        try { form.dispatchEvent(new Event('change', { bubbles: true })); } catch (_) {}
      }
      const bar = document.getElementById('fe-save-bar');
      if (bar) {
        bar.removeAttribute('hidden');
        bar.hidden = false;
        const m = bar.querySelector('.fe-save-bar-msg');
        if (m) m.textContent = 'Unsaved changes';
        document.body.classList.add('has-fe-save-bar');
      }
    }
    function isInModal(target) {
      return target && target.closest && target.closest('#page-events-edit-modal');
    }
    document.addEventListener('input', (e) => {
      if (!isInModal(e.target)) return;
      persistModalToBlock();
      flagDirty();
    }, true);
    document.addEventListener('change', (e) => {
      if (!isInModal(e.target)) return;
      persistModalToBlock();
      flagDirty();
    }, true);

    if (form) {
      form.addEventListener('submit', () => {
        if (edits.size === 0) return;
        let sections;
        try { sections = JSON.parse(hidden.value || '[]') || []; }
        catch (_) { return; }
        let touched = false;
        for (const sec of sections) {
          walkBlocks(sec.blocks || [], (b) => {
            if (edits.has(b.id)) {
              b.data = Object.assign({}, b.data || {}, edits.get(b.id));
              touched = true;
            }
          });
        }
        if (touched) hidden.value = JSON.stringify(sections);
      });
      form.addEventListener('formdata', (e) => {
        if (edits.size === 0) return;
        let sections;
        try { sections = JSON.parse(hidden.value || '[]') || []; }
        catch (_) { return; }
        let touched = false;
        for (const sec of sections) {
          walkBlocks(sec.blocks || [], (b) => {
            if (edits.has(b.id)) {
              b.data = Object.assign({}, b.data || {}, edits.get(b.id));
              touched = true;
            }
          });
        }
        if (touched) {
          const json = JSON.stringify(sections);
          hidden.value = json;
          try { e.formData.set('blocks_json', json); } catch (_) {}
        }
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
