/*
 * Flags format sections of a title page that have a device-specific optimised filter.
 *
 * Looks the current page up by its own path (not via the compare link, which some frozen pages
 * lack) in one of 256 shards, docs/devices/pages/<NN>.json, NN = FNV-1a 32-bit hash of the page
 * path mod 256. Every shard always exists (possibly as {}), so this never requests a missing
 * file. Shards are written by `beqcatalogue/devices.py site`, whose fnv1a_bucket() must match
 * bucketOf() here (tests/fixtures/fnv1a.json pins both).
 *
 * Inserts a badge after each heading whose id matches an optimised entry's anchor, linking to the
 * device comparison view; entries whose anchor is not on the page get a badge under the h1.
 */
(function (global) {
  // this script lives at <site root>/javascripts/devices-flag.js; navigation.instant keeps the
  // script loaded across pages, so resolve the site root once from where it was loaded from
  var script = typeof document !== 'undefined' ? document.currentScript : null;
  var siteRoot = script ? new URL('..', script.src) : null;
  var shardCache = {};

  function bucketOf(value) {
    var bytes = new TextEncoder().encode(value);
    var h = 0x811c9dc5;
    for (var i = 0; i < bytes.length; i++) {
      h = Math.imul(h ^ bytes[i], 0x01000193) >>> 0;
    }
    var bucket = (h % 256).toString(16);
    return bucket.length === 1 ? '0' + bucket : bucket;
  }

  function pagePath(location, root) {
    var path = decodeURIComponent(location.pathname);
    var base = decodeURIComponent(root.pathname);
    if (path.indexOf(base) !== 0) return null;
    path = path.substring(base.length).replace(/index\.html$/, '');
    if (path && path.charAt(path.length - 1) !== '/') path += '/';
    return path;
  }

  function loadShard(bucket) {
    if (!shardCache[bucket]) {
      shardCache[bucket] = fetch(new URL('devices/pages/' + bucket + '.json', siteRoot))
        .then(function (r) { return r.ok ? r.json() : {}; })
        .catch(function () { return {}; });
    }
    return shardCache[bucket];
  }

  function badge(item) {
    var p = document.createElement('p');
    p.className = 'beq-device-badge';
    var a = document.createElement('a');
    a.href = new URL('devices/?t=' + encodeURIComponent(item.key) + '&d=' + encodeURIComponent(item.digest),
                     siteRoot).href;
    a.textContent = 'Optimised for ' + item.profiles.join(', ');
    a.title = 'A device-specific optimised version of this filter is available - compare it';
    p.appendChild(a);
    return p;
  }

  function flagPage() {
    var article = document.querySelector('article');
    if (!article || !siteRoot) return;
    var path = pagePath(window.location, siteRoot);
    if (!path) return;
    loadShard(bucketOf(path)).then(function (shard) {
      var items = shard[path];
      if (!items || !items.length || article.querySelector('.beq-device-badge')) return;
      var h1 = article.querySelector('h1');
      var seen = {};
      items.forEach(function (item) {
        if (seen[item.anchor]) return;
        seen[item.anchor] = true;
        var heading = item.anchor ? article.querySelector('[id="' + CSS.escape(item.anchor) + '"]') : null;
        var target = heading || h1;
        if (target) target.insertAdjacentElement('afterend', badge(item));
      });
    });
  }

  global.BeqDeviceFlag = { bucketOf: bucketOf, pagePath: pagePath };
  if (typeof document$ !== 'undefined') document$.subscribe(flagPage);
})(typeof window !== 'undefined' ? window : globalThis);
