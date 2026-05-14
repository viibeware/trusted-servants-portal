// SPDX-License-Identifier: AGPL-3.0-or-later
/* Per-page FAQ edit modal — two-way binding between the modal's
   inputs (verbatim copy of the homepage FAQ macro markup) and the
   active FAQ block's data inside the page-edit form's blocks_json
   hidden input.

   The FAQ block carries a flat list of items (question + answer +
   icon + icon_size). The modal renders the list dynamically — empty
   server-side, and on pill click we clone the `<template>` once per
   saved item and fill the fields. On every input/change anywhere
   inside the modal we walk the DOM cards in order, rebuild
   `block.data.items`, and write the page form's blocks_json. Add /
   remove / drag-reorder all funnel through the same rebuild so the
   data tracks the DOM.

   Same shape as page_features_modal.js — see that file for the
   detailed flow notes.
*/
(function () {
  function init() {
    const modal = document.getElementById('page-faq-edit-modal');
    if (!modal) return;
    const hidden = document.getElementById('page-blocks-json');
    if (!hidden) return;
    const form = document.getElementById('page-edit-form');
    const list = modal.querySelector('[data-faq-list]');
    const tmpl = modal.querySelector('[data-faq-item-template]');
    const addBtn = modal.querySelector('[data-faq-add]');
    const count = modal.querySelector('[data-faq-count]');
    const max = parseInt(
      (modal.querySelector('[data-faq-editor]') || modal)
        .getAttribute('data-faq-max') || '20', 10);
    if (!list || !tmpl || !addBtn) return;

    let activeBlockId = null;
    const edits = new Map();
    let nextIdx = 0;
    function freshIdx() { return nextIdx++; }

    // ── Card clone helper ────────────────────────────────────────
    // Same string-rewrite as the homepage's FAQ editor JS — swap
    // __IDX__ in the template HTML for a unique counter value, then
    // DOM-insert. tspInitMdEditors wires the side-by-side markdown
    // preview for the freshly-cloned card.
    function cloneCard(item) {
      const idx = freshIdx();
      const html = tmpl.innerHTML.split('__IDX__').join(idx);
      const holder = document.createElement('div');
      holder.innerHTML = html.trim();
      const node = holder.firstElementChild;
      if (!node) return null;
      list.appendChild(node);
      if (item) fillCardFields(node, item);
      if (window.tspInitMdEditors) window.tspInitMdEditors(node);
      return node;
    }

    function fillCardFields(node, item) {
      node.querySelectorAll('[data-faq-card-field]').forEach(inp => {
        const key = inp.dataset.faqCardField;
        const v = item[key];
        if (v != null) inp.value = v;
      });
      // Repaint icon preview from saved ref — same helper as features.
      const iconRef = item.icon || '';
      const preview = node.querySelector('[data-icon-preview]');
      const fieldWrap = node.querySelector('[data-icon-field]');
      if (preview) {
        preview.innerHTML = (iconRef && window.tspRenderIconHtml)
          ? window.tspRenderIconHtml(iconRef) : '';
        if (item.icon_size) preview.style.setProperty('--icon-size', item.icon_size + 'px');
        else preview.style.removeProperty('--icon-size');
      }
      if (fieldWrap) fieldWrap.classList.toggle('has-icon', !!iconRef);
    }

    // ── Read all modal inputs into a block-data shape ─────────────
    // Every `[data-faq-field="<key>"]` input contributes one key on
    // the block.data dict. Generic walk so adding a new field row in
    // the template needs no JS change — the columns / width_mode /
    // pad_x knobs ride this path alongside heading + subheading.
    function readModal() {
      const data = {};
      modal.querySelectorAll('[data-faq-field]').forEach(inp => {
        const key = inp.dataset.faqField;
        if (!key) return;
        data[key] = inp.value || '';
      });
      const items = [];
      list.querySelectorAll('[data-faq-item]').forEach(card => {
        const item = { question: '', answer: '', icon: '', icon_size: '' };
        card.querySelectorAll('[data-faq-card-field]').forEach(inp => {
          const key = inp.dataset.faqCardField;
          item[key] = inp.value || '';
        });
        items.push(item);
      });
      data.items = items;
      return data;
    }

    // ── blocks_json helpers ──────────────────────────────────────
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
      let touchedBlock = null;
      for (const sec of sections) {
        walkBlocks(sec.blocks || [], (b) => {
          if (b.id === activeBlockId) {
            b.data = Object.assign({}, b.data || {}, modalData);
            touched = true;
            touchedBlock = b;
          }
        });
      }
      if (touched) {
        writeSections(sections);
        if (touchedBlock && typeof window.tspSyncStructurePayloadOne === 'function') {
          try { window.tspSyncStructurePayloadOne(activeBlockId, touchedBlock); }
          catch (_) {}
        }
      }
    }

    function populateModalFromBlock(block) {
      if (!block || !block.data) return;
      const data = block.data;
      // Generic walk over every `data-faq-field` input — heading,
      // subheading, columns, width_mode, pad_x all flow through this
      // path. Selects + range inputs both accept assignment to .value.
      // Defaults are encoded in the rendered <option selected> / range
      // value=, so an empty / missing key on the saved block falls
      // back to the input's HTML default rather than going blank.
      modal.querySelectorAll('[data-faq-field]').forEach(inp => {
        const key = inp.dataset.faqField;
        if (!key) return;
        const v = data[key];
        if (v != null && v !== '') {
          inp.value = v;
        }
      });
      // Range output is updated by its 'input' listener (registered
      // below), but on initial populate we need to fire that update
      // synthetically so the readout shows the saved value rather
      // than the slider's HTML default.
      const padInp = modal.querySelector('[data-faq-pad-input]');
      const padOut = modal.querySelector('[data-faq-pad-out]');
      if (padInp && padOut) padOut.textContent = (padInp.value || '0') + 'px';
      list.innerHTML = '';
      nextIdx = 0;
      const items = Array.isArray(data.items) ? data.items : [];
      items.forEach(it => cloneCard(it));
      refreshCount();
    }

    // ── Add / remove / drag-reorder ──────────────────────────────
    function refreshCount() {
      const cards = list.querySelectorAll('[data-faq-item]');
      if (count) {
        count.textContent = cards.length + ' / ' + max + ' item'
                          + (max === 1 ? '' : 's');
      }
      addBtn.disabled = cards.length >= max;
      addBtn.classList.toggle('is-disabled', cards.length >= max);
    }

    addBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const cards = list.querySelectorAll('[data-faq-item]');
      if (cards.length >= max) return;
      const node = cloneCard(null);
      refreshCount();
      persistModalToBlock();
      flagDirty();
      if (node) {
        const qInput = node.querySelector('.fe-faq-card-question');
        if (qInput) qInput.focus();
      }
    });

    list.addEventListener('click', (e) => {
      const rm = e.target.closest('[data-faq-remove]');
      if (!rm) return;
      e.preventDefault();
      const card = rm.closest('[data-faq-item]');
      if (!card) return;
      card.remove();
      refreshCount();
      persistModalToBlock();
      flagDirty();
    });

    // Pointer-driven drag-to-reorder — same shape as features /
    // homepage. DOM order IS the source of truth, so re-reading via
    // readModal() after pointerup yields the new item order
    // automatically.
    let dragging = null;
    list.addEventListener('pointerdown', (e) => {
      const handle = e.target.closest('.fe-faq-card-handle');
      if (!handle) return;
      const card = handle.closest('[data-faq-item]');
      if (!card) return;
      dragging = card;
      card.classList.add('is-dragging');
      try { handle.setPointerCapture(e.pointerId); } catch (_) {}
    });
    list.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      const siblings = Array.from(
        list.querySelectorAll('[data-faq-item]:not(.is-dragging)'));
      for (const sib of siblings) {
        const r = sib.getBoundingClientRect();
        if (e.clientY < r.top + r.height / 2) {
          list.insertBefore(dragging, sib);
          return;
        }
      }
      list.appendChild(dragging);
    });
    function endDrag() {
      if (!dragging) return;
      dragging.classList.remove('is-dragging');
      dragging = null;
      persistModalToBlock();
      flagDirty();
    }
    list.addEventListener('pointerup', endDrag);
    list.addEventListener('pointercancel', endDrag);

    // ── Pill click → populate + open ─────────────────────────────
    document.addEventListener('click', (e) => {
      const pill = e.target.closest('[data-block-type="faq"][data-page-block-id]');
      if (!pill) return;
      if (e.target.closest('[data-be-remove-block]')) return;
      activeBlockId = pill.dataset.pageBlockId;
      let payload = null;
      try { payload = JSON.parse(pill.getAttribute('data-block-payload') || 'null'); }
      catch (_) {}
      if (!payload) payload = findBlock(activeBlockId);
      if (payload) populateModalFromBlock(payload);
    }, true);

    // ── Two-way binding: any input in modal → persist ────────────
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
      return target && target.closest && target.closest('#page-faq-edit-modal');
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

    // ── Late-fire submit / formdata patch ────────────────────────
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

    // Live readout for the side-padding range slider. The existing
    // generic `input` listener at the bottom of this file already
    // serialises every change into the block — this only handles the
    // cosmetic "<value>px" text next to the slider label.
    const padInp = modal.querySelector('[data-faq-pad-input]');
    const padOut = modal.querySelector('[data-faq-pad-out]');
    if (padInp && padOut) {
      const syncPadOut = () => { padOut.textContent = (padInp.value || '0') + 'px'; };
      padInp.addEventListener('input', syncPadOut);
      syncPadOut();
    }

    refreshCount();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
