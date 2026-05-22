/* SPDX-License-Identifier: AGPL-3.0-or-later
 * Product marketing page: reveal-on-scroll + stat count-up. CSS-first; this is
 * just the orchestration. Degrades gracefully without IntersectionObserver.
 */
(function () {
  "use strict";

  var els = document.querySelectorAll(".pp-reveal, .pp-stagger");
  if (!("IntersectionObserver" in window)) {
    els.forEach(function (el) { el.classList.add("in"); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
    els.forEach(function (el) { io.observe(el); });
  }

  function countUp(el) {
    var target = parseFloat(el.getAttribute("data-count"));
    var suffix = el.getAttribute("data-suffix") || "";
    if (isNaN(target)) return;
    var start = null, dur = 1100;
    function step(ts) {
      if (start === null) start = ts;
      var p = Math.min((ts - start) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(target * eased) + suffix;
      if (p < 1) requestAnimationFrame(step);
      else el.textContent = target + suffix;
    }
    requestAnimationFrame(step);
  }

  var band = document.querySelector(".pp-stats");
  if (band && "IntersectionObserver" in window) {
    var done = false;
    var so = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting && !done) {
          done = true;
          band.querySelectorAll("[data-count]").forEach(countUp);
          so.disconnect();
        }
      });
    }, { threshold: 0.4 });
    so.observe(band);
  }

  // Theme toggle — flips data-theme on <html> and persists the choice.
  // Dark is the default; light only when the visitor has explicitly chosen it.
  var root = document.documentElement;
  function effectiveTheme() {
    return root.getAttribute("data-theme") === "light" ? "light" : "dark";
  }
  document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var next = effectiveTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("pp-theme", next); } catch (e) {}
    });
  });
})();
