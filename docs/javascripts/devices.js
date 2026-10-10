/*
 * Client-side "device optimisation" view.
 *
 * Reads ?t=<compare key>[&d=<digest>] (or offers a title search over docs/devices/titles.json),
 * fetches docs/devices/compare/<key>.json (written by `beqcatalogue/devices.py site`, only for
 * titles with at least one optimised entry) and, for the selected entry and each format profile
 * that optimised it, plots:
 *
 *  - the ideal (unrounded RBJ) response, and the response as loaded before/after optimisation
 *  - each loaded response's error vs the ideal, with the profile's matching margin shaded
 *
 * "As loaded" mirrors beqoptimiser's catalogue adapter: before = the published rate-specific
 * coefficients when every filter has them, else RBJ at the profile rate; after = the device
 * catalogue's coefficients; both rounded to float32. The table shows the optimiser's own
 * validated maximum errors; the charts are recomputed here on a coarser grid.
 */
(function () {
  var CHART_JS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js';
  // per profile: [optimised, before] — distinct hues so the dashed "before" line can't be lost against the solid one
  var COLORS = [['#2f6fed', '#e8871e'], ['#8956d6', '#1fa3a3'], ['#d64f8a', '#c9931f'], ['#e0523c', '#3b82c4']];
  var IDEAL_COLOR = '#6b7280';
  var FREQS = window.BeqBiquad ? window.BeqBiquad.logSpace(1, 200, 240) : [];
  var TICKS = [1, 2, 5, 10, 20, 50, 100, 200];

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

  function fetchJson(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error('Not found: ' + url);
      return r.json();
    });
  }

  var titlesPromise = null;
  function loadTitles() {
    if (!titlesPromise) titlesPromise = fetchJson('titles.json');
    return titlesPromise;
  }

  var indexPromise = null;
  function loadIndex() {
    if (!indexPromise) {
      indexPromise = fetchJson('index.json').then(function (index) {
        var byId = {};
        index.profiles.forEach(function (p, i) { p._color = COLORS[i % COLORS.length][0]; p._beforeColor = COLORS[i % COLORS.length][1]; byId[p.id] = p; });
        return byId;
      });
    }
    return indexPromise;
  }

  function variantLabel(entry) {
    var parts = [entry.author];
    if (entry.audioTypes && entry.audioTypes.length) parts.push(entry.audioTypes.join('+'));
    if (entry.season) {
      var s = 'S' + entry.season;
      if (entry.episode) s += 'E' + entry.episode;
      parts.push(s);
    }
    if (entry.edition) parts.push(entry.edition);
    return parts.join(' · ');
  }

  // ideal, before and after responses (dB) for one entry at one profile
  function profileCurves(entry, profile, optimised) {
    var B = window.BeqBiquad;
    var rate = profile.rate;
    var ideal = B.sectionsResponseDb(B.sectionsFromParams(entry.filters, rate), FREQS, rate);
    var sent = B.sectionsFromPublished(entry.filters, rate) || B.sectionsFromParams(entry.filters, rate);
    var round = profile.storage === 'float32' ? B.toFloat32 : function (s) { return s; };
    var before = B.sectionsResponseDb(round(sent), FREQS, rate);
    var after = B.sectionsResponseDb(round(optimised.after.map(B.sectionFromPublished)), FREQS, rate);
    return { ideal: ideal, before: before, after: after };
  }

  function line(label, data, color, dash, extra) {
    var d = { label: label, data: data, borderColor: color, backgroundColor: color, borderDash: dash || [],
              borderWidth: 2, pointRadius: 0, tension: 0.1 };
    for (var k in extra || {}) d[k] = extra[k];
    return d;
  }

  function logXAxis() {
    return {
      type: 'logarithmic',
      title: { display: true, text: 'Frequency (Hz)' },
      ticks: { callback: function (val) { return TICKS.indexOf(Number(val)) !== -1 ? Number(val) : null; } }
    };
  }

  function fmt(v) { return v === null || v === undefined ? '–' : v.toFixed(3) + ' dB'; }

  function initDevicesApp(root) {
    var searchInput = root.querySelector('#beq-devices-search-input');
    var searchResults = root.querySelector('#beq-devices-search-results');
    var selectedTitleEl = root.querySelector('#beq-devices-selected-title');
    var entryEl = root.querySelector('#beq-devices-entry');
    var linksEl = root.querySelector('#beq-devices-links');
    var profilesEl = root.querySelector('#beq-devices-profiles');
    var tableEl = root.querySelector('#beq-devices-table');
    var responseCanvas = root.querySelector('#beq-devices-response');
    var errorCanvas = root.querySelector('#beq-devices-error');
    var charts = { response: null, error: null };
    var state = { key: null, entries: [], entry: null, profiles: {}, hidden: {} };

    function draw(name, canvas, datasets, yTitle) {
      if (charts[name]) {
        charts[name].data.datasets = datasets;
        charts[name].update();
        return;
      }
      charts[name] = new window.Chart(canvas.getContext('2d'), {
        type: 'line',
        data: { labels: FREQS.map(function (f) { return f.toFixed(2); }), datasets: datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          interaction: { mode: 'index', intersect: false },
          scales: { x: logXAxis(), y: { title: { display: true, text: yTitle } } },
          plugins: {
            legend: { position: 'bottom', labels: { filter: function (item) { return item.text !== ''; } } },
            tooltip: { filter: function (item) { return item.dataset.label !== ''; } }
          }
        }
      });
    }

    function render() {
      var entry = state.entry;
      var ids = Object.keys(entry.profiles).filter(function (id) { return state.profiles[id]; }).sort();
      var response = [], error = [], margins = {};
      var idealShown = false;
      ids.forEach(function (id) {
        var profile = state.profiles[id];
        var curves = profileCurves(entry, profile, entry.profiles[id]);
        if (!idealShown) {
          response.push(line('Ideal', curves.ideal, IDEAL_COLOR, [], { borderWidth: 3 }));
          error.push(line('Ideal', FREQS.map(function () { return 0; }), IDEAL_COLOR, [], { borderWidth: 3 }));
          idealShown = true;
        }
        if (state.hidden[id]) return;
        var c = profile._color, cb = profile._beforeColor;
        response.push(line(profile.label + ' — before', curves.before, cb, [6, 4]));
        response.push(line(profile.label + ' — optimised', curves.after, c));
        error.push(line(profile.label + ' — before', curves.before.map(function (v, i) { return v - curves.ideal[i]; }), cb, [6, 4]));
        error.push(line(profile.label + ' — optimised', curves.after.map(function (v, i) { return v - curves.ideal[i]; }), c));
        margins[profile.margin_db] = true;
      });
      Object.keys(margins).forEach(function (m) {
        var v = Number(m);
        var band = 'rgba(63, 174, 92, 0.12)';
        error.push(line('', FREQS.map(function () { return v; }), band, [], { borderWidth: 0 }));
        error.push(line('±' + v + ' dB margin', FREQS.map(function () { return -v; }), band, [],
                        { borderWidth: 0, fill: '-1' }));
      });
      draw('response', responseCanvas, response, 'Gain (dB)');
      draw('error', errorCanvas, error, 'Error vs ideal (dB)');
    }

    function renderTable() {
      var entry = state.entry;
      var rows = Object.keys(entry.profiles).sort().filter(function (id) { return state.profiles[id]; })
        .map(function (id) {
          var p = state.profiles[id], o = entry.profiles[id];
          return '<tr><td>' + p.label + '</td><td>' + (p.rate / 1000) + ' kHz</td><td>' + p.storage +
            '</td><td>' + fmt(o.before_db) + '</td><td>' + fmt(o.after_db) + '</td></tr>';
        });
      tableEl.innerHTML = '<table><thead><tr><th>Profile</th><th>Rate</th><th>Precision</th>' +
        '<th>Max error before</th><th>Max error optimised</th></tr></thead><tbody>' + rows.join('') +
        '</tbody></table><p class="beq-devices-note">Maximum magnitude error vs the ideal filter across ' +
        'the optimiser\'s matching band (default 2–200 Hz), as validated by the optimiser. These are ' +
        'predicted coefficient responses, not hardware measurements. MV adjustment is unchanged (' +
        (entry.mv || '0') + ' dB).</p>';
    }

    function renderProfileToggles() {
      profilesEl.innerHTML = '';
      Object.keys(state.entry.profiles).sort().forEach(function (id) {
        var p = state.profiles[id];
        if (!p) return;
        var wrap = document.createElement('label');
        wrap.className = 'beq-devices-toggle';
        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = !state.hidden[id];
        cb.addEventListener('change', function () {
          state.hidden[id] = !cb.checked;
          render();
        });
        wrap.appendChild(cb);
        var swatch = document.createElement('span');
        swatch.className = 'beq-devices-swatch';
        swatch.style.background = p._color;
        wrap.appendChild(swatch);
        var text = document.createElement('span');
        text.textContent = p.label;
        wrap.appendChild(text);
        profilesEl.appendChild(wrap);
      });
    }

    function renderLinks() {
      var entry = state.entry;
      var links = [];
      if (entry.catalogue_url) links.push('<a href="' + entry.catalogue_url + '">Catalogue entry</a>');
      links.push('<a href="../compare/?t=' + encodeURIComponent(state.key) + '">Compare across authors</a>');
      linksEl.innerHTML = links.join(' · ');
    }

    function selectEntry(entry) {
      state.entry = entry;
      var url = new URL(window.location.href);
      url.searchParams.set('d', entry.digest);
      window.history.replaceState({}, '', url);
      renderLinks();
      renderProfileToggles();
      renderTable();
      render();
    }

    function renderEntryPicker(preferred) {
      entryEl.innerHTML = '';
      var initial = state.entries.filter(function (e) { return e.digest === preferred; })[0] || state.entries[0];
      if (state.entries.length > 1) {
        var select = document.createElement('select');
        state.entries.forEach(function (e, i) {
          var opt = document.createElement('option');
          opt.value = String(i);
          opt.textContent = variantLabel(e);
          if (e === initial) opt.selected = true;
          select.appendChild(opt);
        });
        select.addEventListener('change', function () { selectEntry(state.entries[Number(select.value)]); });
        entryEl.appendChild(select);
      } else {
        entryEl.textContent = variantLabel(initial);
      }
      selectEntry(initial);
    }

    function showTitle(key, digest, titleLabel) {
      selectedTitleEl.textContent = 'Loading…';
      state.key = key;
      Promise.all([fetchJson('compare/' + encodeURIComponent(key) + '.json'), loadIndex(), ensureChartJs()])
        .then(function (results) {
          state.entries = results[0];
          state.profiles = results[1];
          return titleLabel ? titleLabel : loadTitles().then(function (titles) {
            var t = titles.filter(function (x) { return x.key === key; })[0];
            return t ? t.title + (t.year ? ' (' + t.year + ')' : '') : key;
          });
        })
        .then(function (label) {
          selectedTitleEl.textContent = label;
          renderEntryPicker(digest);
        })
        .catch(function (err) {
          selectedTitleEl.textContent = 'No device optimisation is available for this title.';
          console.error(err);
        });
    }

    function renderSearchResults(matches) {
      searchResults.innerHTML = '';
      matches.slice(0, 20).forEach(function (m) {
        var item = document.createElement('div');
        item.className = 'beq-devices-search-result';
        item.textContent = m.title + (m.year ? ' (' + m.year + ')' : '') + ' — ' + m.authors.join(', ');
        item.addEventListener('click', function () {
          searchResults.innerHTML = '';
          searchInput.value = m.title;
          var url = new URL(window.location.href);
          url.searchParams.set('t', m.key);
          url.searchParams.delete('d');
          window.history.replaceState({}, '', url);
          showTitle(m.key, null, m.title + (m.year ? ' (' + m.year + ')' : ''));
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
        renderSearchResults(titles.filter(function (t) { return t.title.toLowerCase().indexOf(q) !== -1; }));
      });
    });

    var params = new URLSearchParams(window.location.search);
    if (params.get('t')) {
      showTitle(params.get('t'), params.get('d'));
    } else {
      selectedTitleEl.textContent = 'Search for a title above, or follow an "Optimised for…" link from a catalogue page.';
    }
  }

  document$.subscribe(function () {
    var root = document.getElementById('beq-devices-app');
    if (root) initDevicesApp(root);
  });
})();
