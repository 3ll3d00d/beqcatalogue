/*
 * Client-side "compare filters across authors" view.
 *
 * Reads ?t=<key> from the URL (or offers a title search), fetches the small per-title JSON
 * from docs/compare/<key>.json (author/format/filters only, no biquad coefficients - see
 * beqcatalogue/__init__.py's build_compare_data), computes each entry's frequency response
 * with biquad.js, and plots them with Chart.js (loaded lazily, only on this page).
 *
 * Uses document$.subscribe rather than a DOMContentLoaded listener because mkdocs-material's
 * navigation.instant swaps page content via fetch and does not fire a fresh page load.
 */
(function () {
  var CHART_JS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js';
  var COLORS = ['#2f6fed', '#e0523c', '#3fae5c', '#c9931f', '#8956d6', '#1fa3a3', '#d64f8a', '#6b7280'];
  var DASHES = [[], [6, 4], [2, 2], [8, 3, 2, 3]];
  var FREQS = window.BeqBiquad ? window.BeqBiquad.logSpace(1, 200, 200) : [];

  var chartJsPromise = null;
  function ensureChartJs() {
    if (window.Chart) return Promise.resolve();
    if (!chartJsPromise) {
      chartJsPromise = new Promise(function (resolve, reject) {
        var s = document.createElement('script');
        s.src = CHART_JS_URL;
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
      });
    }
    return chartJsPromise;
  }

  var titlesPromise = null;
  function loadTitles() {
    if (!titlesPromise) {
      titlesPromise = fetch('titles.json').then(function (r) { return r.json(); });
    }
    return titlesPromise;
  }

  function loadTitle(key) {
    return fetch(key + '.json').then(function (r) {
      if (!r.ok) throw new Error('Not found: ' + key);
      return r.json();
    });
  }

  function variantLabel(entry) {
    var parts = [];
    if (entry.audioTypes && entry.audioTypes.length) parts.push(entry.audioTypes.join('+'));
    if (entry.season) {
      var s = 'S' + entry.season;
      if (entry.episode) s += 'E' + entry.episode;
      parts.push(s);
    }
    if (entry.edition) parts.push(entry.edition);
    return parts.join(' · ');
  }

  function initCompareApp(root) {
    var searchInput = root.querySelector('#beq-compare-search-input');
    var searchResults = root.querySelector('#beq-compare-search-results');
    var selectedTitleEl = root.querySelector('#beq-compare-selected-title');
    var authorsEl = root.querySelector('#beq-compare-authors');
    var canvas = root.querySelector('#beq-compare-chart');
    var chart = null;
    var currentEntries = [];

    function colorFor(author, index, authorIndex) {
      var base = COLORS[authorIndex % COLORS.length];
      return { color: base, dash: DASHES[index % DASHES.length] };
    }

    function renderChart(entries) {
      var authors = [];
      entries.forEach(function (e) {
        if (authors.indexOf(e.author) === -1) authors.push(e.author);
      });
      var perAuthorCount = {};
      var datasets = entries.map(function (entry) {
        var authorIndex = authors.indexOf(entry.author);
        var seenForAuthor = perAuthorCount[entry.author] || 0;
        perAuthorCount[entry.author] = seenForAuthor + 1;
        var style = colorFor(entry.author, seenForAuthor, authorIndex);
        var label = entry.author + (variantLabel(entry) ? ' — ' + variantLabel(entry) : '');
        var data = window.BeqBiquad.cascadeResponseDb(entry.filters, FREQS);
        return {
          label: label,
          data: data,
          borderColor: style.color,
          backgroundColor: style.color,
          borderDash: style.dash,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.15,
          hidden: !entry._checked
        };
      });

      if (chart) {
        chart.data.datasets = datasets;
        chart.update();
        return;
      }

      chart = new window.Chart(canvas.getContext('2d'), {
        type: 'line',
        data: { labels: FREQS.map(function (f) { return f.toFixed(1); }), datasets: datasets },
        options: {
          responsive: true,
          animation: false,
          interaction: { mode: 'index', intersect: false },
          scales: {
            x: {
              type: 'logarithmic',
              title: { display: true, text: 'Frequency (Hz)' },
              ticks: {
                callback: function (val) {
                  var n = Number(val);
                  return [1, 2, 5, 10, 20, 50, 100, 200].indexOf(n) !== -1 ? n : null;
                }
              }
            },
            y: { title: { display: true, text: 'Gain (dB)' } }
          },
          plugins: { legend: { position: 'bottom' } }
        }
      });
    }

    function renderAuthorToggles(entries) {
      authorsEl.innerHTML = '';
      entries.forEach(function (entry, idx) {
        var id = 'beq-compare-toggle-' + idx;
        var wrap = document.createElement('label');
        wrap.className = 'beq-compare-toggle';
        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.id = id;
        cb.checked = true;
        entry._checked = true;
        cb.addEventListener('change', function () {
          entry._checked = cb.checked;
          renderChart(currentEntries);
        });
        wrap.appendChild(cb);
        var text = document.createElement('span');
        text.textContent = ' ' + entry.author + (variantLabel(entry) ? ' — ' + variantLabel(entry) : '');
        wrap.appendChild(text);
        authorsEl.appendChild(wrap);
      });
    }

    function showTitle(key, titleLabel) {
      selectedTitleEl.textContent = 'Loading…';
      loadTitle(key).then(function (entries) {
        currentEntries = entries;
        selectedTitleEl.textContent = titleLabel || key;
        renderAuthorToggles(entries);
        return ensureChartJs();
      }).then(function () {
        renderChart(currentEntries);
      }).catch(function (err) {
        selectedTitleEl.textContent = 'Could not load data for this title.';
        console.error(err);
      });
    }

    function renderSearchResults(matches) {
      searchResults.innerHTML = '';
      matches.slice(0, 20).forEach(function (m) {
        var item = document.createElement('div');
        item.className = 'beq-compare-search-result';
        item.textContent = m.title + (m.year ? ' (' + m.year + ')' : '') + ' — ' + m.authors.length + ' author(s)';
        item.addEventListener('click', function () {
          searchResults.innerHTML = '';
          searchInput.value = m.title;
          var url = new URL(window.location.href);
          url.searchParams.set('t', m.key);
          window.history.replaceState({}, '', url);
          showTitle(m.key, m.title);
        });
        searchResults.appendChild(item);
      });
    }

    searchInput.addEventListener('input', function () {
      var q = searchInput.value.trim().toLowerCase();
      if (q.length < 2) {
        searchResults.innerHTML = '';
        return;
      }
      loadTitles().then(function (titles) {
        var matches = titles.filter(function (t) { return t.title.toLowerCase().indexOf(q) !== -1; });
        renderSearchResults(matches);
      });
    });

    var params = new URLSearchParams(window.location.search);
    var key = params.get('t');
    if (key) {
      showTitle(key);
    } else {
      selectedTitleEl.textContent = 'Search for a title above to compare its filters across authors.';
    }
  }

  document$.subscribe(function () {
    var root = document.getElementById('beq-compare-app');
    if (root) initCompareApp(root);
  });
})();
