// SPDX-License-Identifier: AGPL-3.0-or-later
/* Per-page features edit modal — two-way binding between the modal's
   inputs (verbatim copy of the homepage features macro markup) and the
   active Features block's data inside the page-edit form's
   blocks_json hidden input.

   The features block carries a list of items (icon + title + body +
   href). The modal renders cards dynamically — server-side the list
   is empty, and on pill click we clone the `<template>` once per saved
   item and fill the fields. On every input/change anywhere in the
   modal we walk the DOM cards in order, rebuild `block.data.items`,
   and write the page form's blocks_json. Add / remove / reorder all
   funnel through the same rebuild so the data tracks the DOM.

   Card index counter is local to the modal and resets every pill
   click — it only matters so the icon picker's hidden-input IDs
   (`#feat-card-<idx>-icon`) stay unique within the current snapshot.
*/
(function () {
  function init() {
    const modal = document.getElementById('page-features-edit-modal');
    if (!modal) return;
    const hidden = document.getElementById('page-blocks-json');
    if (!hidden) return;
    const form = document.getElementById('page-edit-form');
    const list = modal.querySelector('[data-features-list]');
    const tmpl = modal.querySelector('[data-features-card-template]');
    const addBtn = modal.querySelector('[data-features-add]');
    const count = modal.querySelector('[data-features-count]');
    const max = parseInt(
      (modal.querySelector('[data-features-editor]') || modal)
        .getAttribute('data-features-max') || '6', 10);
    if (!list || !tmpl || !addBtn) return;

    let activeBlockId = null;
    const edits = new Map();    // blockId → latest data object
    let nextIdx = 0;

    // ── Card index allocator ─────────────────────────────────────
    // Each `_feature_card_row(idx)` server-side stamps `id="feat-card-<idx>-icon"`
    // on its hidden inputs so the shared icon picker can write into the
    // right card via selector. Page-modal indices need to be unique
    // within the current modal state but don't matter beyond that —
    // we reset to 0 on every pill open.
    function freshIdx() { return nextIdx++; }

    // ── Card clone helper ────────────────────────────────────────
    // Same string-rewrite approach as the homepage's features-editor
    // JS (lines 1396-1416 of frontend_homepage.html): swap __IDX__ in
    // the template HTML for a unique counter value, then DOM-insert.
    // After insertion we initialise any markdown editor inside the
    // card so its Write/Preview tabs work (`tspInitMdEditors` is the
    // shared helper from app.js).
    function cloneCard(item) {
      const idx = freshIdx();
      const html = tmpl.innerHTML.split('__IDX__').join(idx);
      const holder = document.createElement('div');
      holder.innerHTML = html.trim();
      const node = holder.firstElementChild;
      if (!node) return null;
      list.appendChild(node);
      // Fill fields from the item data BEFORE we wire the MD editor —
      // the editor reads the textarea on mount and renders the
      // preview, so we want it to see the saved value, not an empty
      // textarea.
      if (item) fillCardFields(node, item);
      if (window.tspInitMdEditors) window.tspInitMdEditors(node);
      return node;
    }

    function fillCardFields(node, item) {
      // Each input carries `data-features-card-field="<key>"` matching
      // the item-dict's keys. open_in_new_tab is the lone checkbox.
      node.querySelectorAll('[data-features-card-field]').forEach(inp => {
        const key = inp.dataset.featuresCardField;
        const v = item[key];
        if (inp.type === 'checkbox') {
          inp.checked = !!v;
        } else if (v != null) {
          inp.value = v;
        }
      });
      // Repaint the icon preview from the saved ref. The icon picker
      // only updates the preview when the user goes through its modal
      // — populating the hidden input directly leaves the preview
      // blank, so we render the SVG ourselves via the global helper
      // app.js exposes (window.tspRenderIconHtml).
      const iconRef = item.icon || '';
      const preview = node.querySelector('[data-icon-preview]');
      const fieldWrap = node.querySelector('[data-icon-field]');
      if (preview) {
        preview.innerHTML = (iconRef && window.tspRenderIconHtml)
          ? window.tspRenderIconHtml(iconRef) : '';
        if (item.icon_size) preview.style.setProperty('--icon-size', item.icon_size + 'px');
        else preview.style.removeProperty('--icon-size');
        if (item.icon_color) preview.style.color = item.icon_color;
        else preview.style.color = '';
      }
      if (fieldWrap) fieldWrap.classList.toggle('has-icon', !!iconRef);
    }

    // ── Read all modal inputs into a block-data shape ─────────────
    function readModal() {
      const data = {};
      data.heading = (modal.querySelector('[data-features-field="heading"]') || {}).value || '';
      data.subheading = (modal.querySelector('[data-features-field="subheading"]') || {}).value || '';
      data.cta_label = (modal.querySelector('[data-features-field="cta_label"]') || {}).value || '';
      data.cta_url   = (modal.querySelector('[data-features-field="cta_url"]')   || {}).value || '';
      data.cta_style = (modal.querySelector('[data-features-field="cta_style"]') || {}).value || 'primary';
      const ntInp = modal.querySelector('[data-features-field="cta_new_tab"]');
      data.cta_new_tab = !!(ntInp && ntInp.checked);
      const items = [];
      list.querySelectorAll('[data-features-card]').forEach(card => {
        const item = {
          icon: '', icon_color: '', icon_size: '',
          title: '', body: '', href: '', open_in_new_tab: false,
          button_label: '', button_style: 'primary',
        };
        card.querySelectorAll('[data-features-card-field]').forEach(inp => {
          const key = inp.dataset.featuresCardField;
          if (inp.type === 'checkbox') item[key] = !!inp.checked;
          else item[key] = inp.value || '';
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
      const headingInp = modal.querySelector('[data-features-field="heading"]');
      if (headingInp) headingInp.value = data.heading || '';
      const subInp = modal.querySelector('[data-features-field="subheading"]');
      if (subInp) subInp.value = data.subheading || '';
      const ctaLblInp = modal.querySelector('[data-features-field="cta_label"]');
      if (ctaLblInp) ctaLblInp.value = data.cta_label || '';
      const ctaUrlInp = modal.querySelector('[data-features-field="cta_url"]');
      if (ctaUrlInp) ctaUrlInp.value = data.cta_url || '';
      const ctaStyleInp = modal.querySelector('[data-features-field="cta_style"]');
      if (ctaStyleInp) ctaStyleInp.value = data.cta_style || 'primary';
      const ctaNtInp = modal.querySelector('[data-features-field="cta_new_tab"]');
      if (ctaNtInp) ctaNtInp.checked = !!data.cta_new_tab;
      // Rebuild the cards list from scratch — wipe whatever's there
      // from a previous pill click, reset the idx counter so the new
      // cards get fresh unique IDs.
      list.innerHTML = '';
      nextIdx = 0;
      const items = Array.isArray(data.items) ? data.items : [];
      items.forEach(it => cloneCard(it));
      refreshCount();
    }

    // ── Add / remove / drag-reorder ──────────────────────────────
    function refreshCount() {
      const cards = list.querySelectorAll('[data-features-card]');
      if (count) {
        count.textContent = cards.length + ' / ' + max + ' card'
                          + (max === 1 ? '' : 's');
      }
      addBtn.disabled = cards.length >= max;
      addBtn.classList.toggle('is-disabled', cards.length >= max);
    }

    addBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const cards = list.querySelectorAll('[data-features-card]');
      if (cards.length >= max) return;
      const node = cloneCard(null);
      refreshCount();
      persistModalToBlock();
      flagDirty();
      if (node) {
        const titleInput = node.querySelector('.fe-feat-card-title');
        if (titleInput) titleInput.focus();
      }
    });

    list.addEventListener('click', (e) => {
      const rm = e.target.closest('[data-features-remove]');
      if (!rm) return;
      e.preventDefault();
      const card = rm.closest('[data-features-card]');
      if (!card) return;
      card.remove();
      refreshCount();
      persistModalToBlock();
      flagDirty();
    });

    // Pointer-driven drag-to-reorder — verbatim port of the homepage
    // features-editor implementation (frontend_homepage.html lines
    // 1437-1467). Cards reorder live; DOM order IS the source of
    // truth, so re-reading via readModal() after pointerup yields
    // the new item order automatically.
    let dragging = null;
    list.addEventListener('pointerdown', (e) => {
      const handle = e.target.closest('.fe-feat-card-handle');
      if (!handle) return;
      const card = handle.closest('[data-features-card]');
      if (!card) return;
      dragging = card;
      card.classList.add('is-dragging');
      try { handle.setPointerCapture(e.pointerId); } catch (_) {}
    });
    list.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      const siblings = Array.from(
        list.querySelectorAll('[data-features-card]:not(.is-dragging)'));
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
      const pill = e.target.closest('[data-block-type="features"][data-page-block-id]');
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
      return target && target.closest && target.closest('#page-features-edit-modal');
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

    refreshCount();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
