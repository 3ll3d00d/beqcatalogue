/*
 * Port of beqcatalogue/iir.py's biquad coefficient formulas (RBJ cookbook) so the browser can
 * recompute a filter's frequency response directly from {type, freq, gain, q} without needing
 * the server to ship the exact a/b coefficients for every entry.
 */
(function (global) {
  var FS = 96000; // matches the fs used when the catalogue's filters were generated

  function coeffsFor(type, freq, q, gain) {
    var w0 = 2.0 * Math.PI * freq / FS;
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

  function magnitudeDb(c, freqHz) {
    var w = 2.0 * Math.PI * freqHz / FS;
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
  function cascadeResponseDb(filters, freqs) {
    var totals = new Array(freqs.length).fill(0);
    filters.forEach(function (f) {
      var c = coeffsFor(f.type, f.freq, f.q, f.gain);
      var count = f.count || 1;
      for (var i = 0; i < freqs.length; i++) {
        totals[i] += count * magnitudeDb(c, freqs[i]);
      }
    });
    return totals;
  }

  global.BeqBiquad = {
    logSpace: logSpace,
    cascadeResponseDb: cascadeResponseDb
  };
})(window);
