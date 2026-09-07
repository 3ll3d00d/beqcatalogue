---
search:
  exclude: true
---

# Compare filters across authors

Pick a title (or follow a "Compare across authors" link from any catalogue page) to overlay
the frequency response of every author's filters for that title on one chart.

<div id="beq-compare-app">
  <div class="beq-compare-search">
    <input type="search" id="beq-compare-search-input" placeholder="Search for a title..." autocomplete="off" />
    <div id="beq-compare-search-results"></div>
  </div>
  <div id="beq-compare-selected-title"></div>
  <div id="beq-compare-authors"></div>
  <div class="beq-compare-chart-wrap">
    <canvas id="beq-compare-chart"></canvas>
  </div>
</div>
