---
search:
  exclude: true
---

# Device optimisation

Devices store filter coefficients with limited precision, which can shift a filter's response
noticeably at very low frequencies. For each known device format, the catalogue publishes an
optimised version of every filter where that improves the device's realised response. Pick a
title (or follow an "Optimised for…" link from any catalogue page) to compare the ideal filter
with what the device loads before and after optimisation.

<div id="beq-devices-app">
  <div class="beq-devices-search">
    <input type="search" id="beq-devices-search-input" placeholder="Search optimised titles..." autocomplete="off" />
    <div id="beq-devices-search-results"></div>
  </div>
  <div id="beq-devices-selected-title"></div>
  <div id="beq-devices-entry"></div>
  <div id="beq-devices-links"></div>
  <div id="beq-devices-profiles"></div>
  <div class="beq-devices-chart-wrap">
    <canvas id="beq-devices-response"></canvas>
  </div>
  <div class="beq-devices-chart-wrap">
    <canvas id="beq-devices-error"></canvas>
  </div>
  <div id="beq-devices-table"></div>
</div>

Device catalogues for integrations are published per format profile; see
[the profile index](index.json).
