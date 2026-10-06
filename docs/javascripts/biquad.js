/*
 * Port of beqcatalogue/iir.py's biquad coefficient formulas (RBJ cookbook) so the browser can
 * recompute a filter's frequency response directly from {type, freq, gain, q} without needing
 * the server to ship the exact a/b coefficients for every entry.
 *
 * The device view also evaluates explicit published coefficients ({b: [b0,b1,b2], a: [a1,a2]}
 * decimal strings with additive feedback, as in filters[*].biquads and docs/devices/<id>.json),
 * optionally rounded to float32 with Math.fround to model what a float32 device stores.
 */
(function (global) {
  var FS = 96000; // matches the fs used when the catalogue's filters were generated

  function coeffsFor(type, freq, q, gain, fs) {
    var w0 = 2.0 * Math.PI * freq / (fs || FS);
    var cosW0 = Math.cos(w0);
    var sinW0 = Math.sin(w0);
    var alpha = sinW0 / (2.0 * q);
    var A = Math.pow(10.0, gain / 40.0);
    var a0, a1, a2, b0, b1, b2;

    if (type === 'LowShelf') {
      var sqrtA = Math.sqrt(A);
      a0 = (A + 1) + (A - 1) * cosW0 + 2.0 * sqrtA * alpha;
      a1 = -2.0 * ((A - 1) + (A + 1) * cosW0);
      a2 = (A + 1) + (A - 1) * cosW0 - 2.0 * sqrtA * alpha;
      b0 = A * ((A + 1) - (A - 1) * cosW0 + 2.0 * sqrtA * alpha);
      b1 = 2.0 * A * ((A - 1) - (A + 1) * cosW0);
      b2 = A * ((A + 1) - (A - 1) * cosW0 - 2.0 * sqrtA * alpha);
    } else if (type === 'HighShelf') {
      var sqrtA2 = Math.sqrt(A);
      a0 = (A + 1) - (A - 1) * cosW0 + 2.0 * sqrtA2 * alpha;
      a1 = 2.0 * ((A - 1) - (A + 1) * cosW0);
      a2 = (A + 1) - (A - 1) * cosW0 - 2.0 * sqrtA2 * alpha;
      b0 = A * ((A + 1) + (A - 1) * cosW0 + 2.0 * sqrtA2 * alpha);
      b1 = -2.0 * A * ((A - 1) + (A + 1) * cosW0);
      b2 = A * ((A + 1) + (A - 1) * cosW0 - 2.0 * sqrtA2 * alpha);
    } else {
      // PeakingEQ (default)
      a0 = 1.0 + alpha / A;
      a1 = -2.0 * cosW0;
      a2 = 1.0 - alpha / A;
      b0 = 1.0 + alpha * A;
      b1 = -2.0 * cosW0;
      b2 = 1.0 - alpha * A;
    }

    return { b0: b0 / a0, b1: b1 / a0, b2: b2 / a0, a1: a1 / a0, a2: a2 / a0 };
  }

  function magnitudeDb(c, freqHz, fs) {
    var w = 2.0 * Math.PI * freqHz / (fs || FS);
    var cos1 = Math.cos(w), sin1 = Math.sin(w);
    var cos2 = Math.cos(2 * w), sin2 = Math.sin(2 * w);
    var numRe = c.b0 + c.b1 * cos1 + c.b2 * cos2;
    var numIm = -c.b1 * sin1 - c.b2 * sin2;
    var denRe = 1 + c.a1 * cos1 + c.a2 * cos2;
    var denIm = -c.a1 * sin1 - c.a2 * sin2;
    var numMag = Math.hypot(numRe, numIm);
    var denMag = Math.hypot(denRe, denIm);
    if (denMag === 0) return 0;
    return 20 * Math.log10(numMag / denMag);
  }

  function logSpace(min, max, points) {
    var out = new Array(points);
    var logMin = Math.log10(min), logMax = Math.log10(max);
    for (var i = 0; i < points; i++) {
      var t = points === 1 ? 0 : i / (points - 1);
      out[i] = Math.pow(10, logMin + t * (logMax - logMin));
    }
    return out;
  }

  // sums the dB contribution (repeated `count` times) of every filter in `filters`
  // across `freqs`, returning one dB value per frequency for the cascaded response
  function cascadeResponseDb(filters, freqs, fs) {
    var totals = new Array(freqs.length).fill(0);
    filters.forEach(function (f) {
      var c = coeffsFor(f.type, f.freq, f.q, f.gain, fs);
      var count = f.count || 1;
      for (var i = 0; i < freqs.length; i++) {
        totals[i] += count * magnitudeDb(c, freqs[i], fs);
      }
    });
    return totals;
  }

  // one coefficient set per section, with counts expanded, from RBJ parameters
  function sectionsFromParams(filters, fs) {
    var out = [];
    filters.forEach(function (f) {
      var c = coeffsFor(f.type, f.freq, f.q, f.gain, fs);
      for (var i = 0; i < (f.count || 1); i++) out.push(c);
    });
    return out;
  }

  // published coefficients use additive feedback: y += a1*y[n-1] + a2*y[n-2], so the
  // denominator is 1 - a1 z^-1 - a2 z^-2
  function sectionFromPublished(bq) {
    return { b0: Number(bq.b[0]), b1: Number(bq.b[1]), b2: Number(bq.b[2]), a1: -Number(bq.a[0]), a2: -Number(bq.a[1]) };
  }

  // the published rate-specific coefficients when every filter has them, else null
  function sectionsFromPublished(filters, fs) {
    var out = [];
    for (var j = 0; j < filters.length; j++) {
      var f = filters[j];
      var bq = f.biquads && f.biquads[String(fs)];
      if (!bq) return null;
      var c = sectionFromPublished(bq);
      for (var i = 0; i < (f.count || 1); i++) out.push(c);
    }
    return out;
  }

  function toFloat32(sections) {
    return sections.map(function (c) {
      return { b0: Math.fround(c.b0), b1: Math.fround(c.b1), b2: Math.fround(c.b2),
               a1: Math.fround(c.a1), a2: Math.fround(c.a2) };
    });
  }

  function sectionsResponseDb(sections, freqs, fs) {
    var totals = new Array(freqs.length).fill(0);
    sections.forEach(function (c) {
      for (var i = 0; i < freqs.length; i++) totals[i] += magnitudeDb(c, freqs[i], fs);
    });
    return totals;
  }

  global.BeqBiquad = {
    logSpace: logSpace,
    cascadeResponseDb: cascadeResponseDb,
    sectionsFromParams: sectionsFromParams,
    sectionsFromPublished: sectionsFromPublished,
    sectionFromPublished: sectionFromPublished,
    toFloat32: toFloat32,
    sectionsResponseDb: sectionsResponseDb
  };
})(typeof window !== 'undefined' ? window : globalThis);
