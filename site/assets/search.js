/**
 * MandiBhav by GramIQ — Client-Side Search
 * No external dependencies. Loads search.json and filters in-memory.
 */

(function () {
  'use strict';

  const INPUT = document.getElementById('search-input');
  const RESULTS = document.getElementById('search-results');
  if (!INPUT || !RESULTS) return;

  let INDEX = [];
  let loaded = false;

  /* Load search.json relative to site root */
  function resolveSearchJsonUrl() {
    /* Works for both root deployments and subdirectory (gh-pages) deployments */
    const base = document.querySelector('meta[name="site-base-url"]');
    const baseUrl = base ? base.content.replace(/\/$/, '') : '';
    return baseUrl + '/search.json';
  }

  function loadIndex() {
    if (loaded) return Promise.resolve();
    return fetch(resolveSearchJsonUrl())
      .then(function (r) { return r.json(); })
      .then(function (data) {
        INDEX = data;
        loaded = true;
      })
      .catch(function () {
        RESULTS.innerHTML = '<p style="color:var(--text-muted);font-size:.85rem">Search unavailable.</p>';
        RESULTS.style.display = 'block';
      });
  }

  function normalize(str) {
    return str.toLowerCase().replace(/\s+/g, ' ').trim();
  }

  function highlight(text, query) {
    if (!query) return text;
    const re = new RegExp('(' + query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
    return text.replace(re, '<mark style="background:rgba(34,197,94,0.25);color:inherit;border-radius:2px">$1</mark>');
  }

  function typeLabel(type) {
    const map = {
      daily_commodity_report: 'National Report',
      state_market_report:    'State Report',
      market_spotlight:       'Market Spotlight',
      best_market_today:      'Best Market',
      top_gainers_losers:     'Gainers & Losers',
    };
    return map[type] || type;
  }

  function renderResults(items, query) {
    if (items.length === 0) {
      RESULTS.innerHTML =
        '<p style="color:var(--text-muted);font-size:.85rem;padding:.5rem 0">No results for "' +
        query + '"</p>';
      RESULTS.style.display = 'block';
      return;
    }

    const html = items.slice(0, 12).map(function (item) {
      const tagClass = item.commodity === 'cotton' ? 'tag-cotton' : 'tag-soybean';
      return [
        '<a href="' + item.url + '" class="article-list-item" style="text-decoration:none">',
        '  <div>',
        '    <span class="card-tag ' + tagClass + '">' + item.commodity.toUpperCase() + '</span>',
        '    <span class="card-tag tag-national" style="margin-left:4px">' + typeLabel(item.type) + '</span>',
        '    <div class="article-list-title" style="margin-top:6px">' + highlight(item.title, query) + '</div>',
        '    <div class="article-list-meta" style="margin-top:4px">' + item.date + ' · ' + item.language.toUpperCase() + '</div>',
        '  </div>',
        '  <span class="article-list-arrow">→</span>',
        '</a>',
      ].join('\n');
    }).join('\n');

    RESULTS.innerHTML = html;
    RESULTS.style.display = 'block';
  }

  let debounceTimer;

  INPUT.addEventListener('input', function () {
    const query = normalize(this.value);

    clearTimeout(debounceTimer);

    if (query.length < 2) {
      RESULTS.innerHTML = '';
      RESULTS.style.display = 'none';
      return;
    }

    debounceTimer = setTimeout(function () {
      loadIndex().then(function () {
        const words = query.split(' ').filter(Boolean);
        const matches = INDEX.filter(function (item) {
          const haystack = normalize(item.title + ' ' + item.commodity + ' ' + (item.state || '') + ' ' + (item.market || ''));
          return words.every(function (w) { return haystack.includes(w); });
        });
        renderResults(matches, query);
      });
    }, 200);
  });

  INPUT.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      this.value = '';
      RESULTS.innerHTML = '';
      RESULTS.style.display = 'none';
    }
  });

  /* Close results when clicking outside */
  document.addEventListener('click', function (e) {
    if (!INPUT.contains(e.target) && !RESULTS.contains(e.target)) {
      RESULTS.style.display = 'none';
    }
  });

  /* FAQ accordion */
  document.querySelectorAll('.faq-question').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const item = this.closest('.faq-item');
      const isOpen = item.classList.contains('open');
      /* Close all */
      document.querySelectorAll('.faq-item.open').forEach(function (i) {
        i.classList.remove('open');
      });
      if (!isOpen) item.classList.add('open');
    });
  });

})();
