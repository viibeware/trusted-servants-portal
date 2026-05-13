// SPDX-License-Identifier: AGPL-3.0-or-later
/* Per-page meetings-list edit modal — two-way binding between the
   modal's inputs (verbatim copy of the homepage meetings macro markup)
   and the active Meetings block's data inside the page-edit form's
   blocks_json hidden input.

   Flow mirrors page_hero_modal.js:
     1. Admin clicks a Meetings pill. The pill carries
        `data-page-block-id` (the block's UUID) and `data-block-payload`
        (the block's current JSON).
     2. Existing `[data-open-modal]` handler opens
        `#page-meetings-edit-modal`. Our `click` interceptor captures
        the block id, parses the payload, and writes every value into
        the matching `[data-meetings-field]` input.
     3. Admin edits anything. Our `input` / `change` listener at the
        document level reads every `[data-meetings-field]`, rebuilds
        the block's data, walks the hidden input's blocks_json to
        replace the matching block, and writes back. Bubbling `input`
        event on the form + save-bar reveal marks it dirty.

   The IIFE body is wrapped in a DOMContentLoaded run-once because the
   page-edit template loads `page_meetings_modal.js` BEFORE the
   `_page_meetings_modal.html` include further down the document body
   — same pattern as the hero modal.
*/
(function () {
  function init() {
    const modal = document.getElementById('page-meetings-edit-modal');
    if (!modal) return;
    const hidden = document.getElementById('page-blocks-json');
    if (!hidden) return;
    const form = document.getElementById('page-edit-form');

    // ── Active block tracking ─────────────────────────────────────
    let activeBlockId = null;
    // Per-block latest data, populated on every modal edit. The
    // BlockEditor (in `#page-layout-edit-modal`) auto-mounts on every
    // pill click — even when the click opens OUR modal — and its
    // form-submit handler in `frontend_page_edit.html` writes
    // `editor.serialize()` over `hidden.value` right before submit.
    // For meetings blocks edited through this modal that path returns
    // stale data, wiping our edits. We track every edit here and patch
    // it back into `hidden.value` in a late-fire submit listener
    // (registered in init, runs after the inline serializer because
    // external scripts attach first).
    const edits = new Map();   // blockId → latest data object

    // ── Field schema ──────────────────────────────────────────────
    // Range inputs and the schedule-line counter are integers; the
    // three toggles are booleans; everything else is a plain string.
    const NUM_FIELDS = new Set(['max_count', 'show_first_n', 'stagger_ms']);
    const BOOL_FIELDS = new Set(['group_by_day', 'show_type_chip', 'show_schedule']);

    // ── Read all modal inputs into a block-data shape ─────────────
    function readModal() {
      const data = {};
      modal.querySelectorAll('[data-meetings-field]').forEach(inp => {
        const key = inp.dataset.meetingsField;
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

    // ── Walk blocks_json + find / replace the active block ────────
    function readSections() {
      try { return JSON.parse(hidden.value || '[]') || []; }
      catch (_) { return []; }
    }
    function writeSections(sections) {
      hidden.value = JSON.stringify(sections);
      // Mirror page_hero_modal's triple-dispatch so save bar / form
      // dirty trackers all light up.
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

    // ── Populate modal inputs from a block's data ─────────────────
    function populateModalFromBlock(block) {
      if (!block || !block.data) return;
      const data = block.data;
      modal.querySelectorAll('[data-meetings-field]').forEach(inp => {
        const key = inp.dataset.meetingsField;
        if (!key) return;
        const v = data[key];
        if (BOOL_FIELDS.has(key) || inp.type === 'checkbox') {
          inp.checked = !!v;
        } else if (v != null) {
          inp.value = v;
        }
      });
      // Refresh slider readouts.
      modal.querySelectorAll('[data-slider-input]').forEach(inp => {
        const wrap = inp.closest('.nav-megalink-field');
        const out = wrap && wrap.querySelector('[data-slider-out]');
        if (out) out.textContent = inp.value;
      });
    }

    // ── Slider readouts ──────────────────────────────────────────
    // The macro's range inputs sit alongside an <output data-slider-out>
    // that needs to track the slider value live. Same pattern the
    // homepage uses; we wire it here so the modal is self-contained.
    modal.querySelectorAll('[data-slider-input]').forEach(inp => {
      const wrap = inp.closest('.nav-megalink-field');
      const out = wrap && wrap.querySelector('[data-slider-out]');
      if (!out) return;
      inp.addEventListener('input', () => { out.textContent = inp.value; });
    });

    // ── Pill click → populate + open ──────────────────────────────
    // Capture phase so we run BEFORE the generic [data-open-modal]
    // handler binds the modal-open animation; we just identify the
    // block to populate and let the open proceed normally.
    document.addEventListener('click', (e) => {
      const pill = e.target.closest('[data-block-type="meetings"][data-page-block-id]');
      if (!pill) return;
      // Ignore clicks on the remove × button inside the pill.
      if (e.target.closest('[data-be-remove-block]')) return;
      activeBlockId = pill.dataset.pageBlockId;
      let payload = null;
      try { payload = JSON.parse(pill.getAttribute('data-block-payload') || 'null'); }
      catch (_) {}
      if (!payload) payload = findBlock(activeBlockId);
      if (payload) populateModalFromBlock(payload);
    }, true);

    // ── Two-way binding: any input in the modal → persist ─────────
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
      return target && target.closest && target.closest('#page-meetings-edit-modal');
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

    // ── Late-fire submit listener ────────────────────────────────
    // Runs AFTER the inline submit handler in `frontend_page_edit.html`
    // (which writes `editor.serialize()` over hidden.value). We walk
    // the just-written JSON, find every meetings block we've edited,
    // and patch its data back in. Belt-and-braces guard against the
    // BlockEditor's stale-state serialize wiping our work.
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
  }   // ── close init() ──

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
