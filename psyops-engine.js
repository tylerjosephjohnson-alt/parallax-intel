/* =========================================
   PSYOPS ENGINE — JavaScript
   Vantage Geopolitical Intelligence Platform
   ========================================= */

/* --- Collapse / Expand campaign cards --- */
function psyopToggleCard(header) {
  var card = header.closest('.psyop-card');
  if (card) card.classList.toggle('expanded');
}

/* --- Tab switching (scoped to the card) --- */
function psyopSwitchTab(el, tabId) {
  var card = el.closest('.psyop-card');
  if (!card) return;
  var tabs = card.querySelectorAll('.psyop-tab');
  var panes = card.querySelectorAll('.psyop-tab-content');
  for (var i = 0; i < tabs.length; i++) tabs[i].classList.remove('active');
  for (var i = 0; i < panes.length; i++) panes[i].classList.remove('active');
  el.classList.add('active');
  var target = document.getElementById(tabId);
  if (target) target.classList.add('active');
}

/* --- Technique card expand/collapse --- */
function psyopToggleTechnique(header) {
  var body = header.nextElementSibling;
  if (body) body.classList.toggle('open');
}

/* --- Filter state --- */
var psyopFilters = { status: 'all', type: 'all', conf: 'all' };

function psyopSetFilter(btn, category, value) {
  psyopFilters[category] = value;
  var row = btn.parentElement;
  var btns = row.querySelectorAll('.psyops-filter-btn');
  for (var i = 0; i < btns.length; i++) btns[i].classList.remove('pf-active');
  if (value !== 'all') btn.classList.add('pf-active');
  psyopApplyFilters();
}

function psyopApplyFilters() {
  var searchEl = document.querySelector('.psyops-search');
  var query = searchEl ? searchEl.value.toLowerCase() : '';
  var list = document.getElementById('psyop-list');
  if (!list) return;
  var cards = list.querySelectorAll('.psyop-card');
  var visible = 0;

  for (var i = 0; i < cards.length; i++) {
    var c = cards[i];
    var matchStatus = psyopFilters.status === 'all' || c.getAttribute('data-status') === psyopFilters.status;
    var matchType = psyopFilters.type === 'all' || c.getAttribute('data-type') === psyopFilters.type;
    var matchConf = psyopFilters.conf === 'all' || c.getAttribute('data-conf') === psyopFilters.conf;
    var searchText = (c.getAttribute('data-search') || '') + ' ' + (c.querySelector('.psyop-name') ? c.querySelector('.psyop-name').textContent.toLowerCase() : '');
    var matchSearch = !query || searchText.indexOf(query) !== -1;

    if (matchStatus && matchType && matchConf && matchSearch) {
      c.style.display = '';
      visible++;
    } else {
      c.style.display = 'none';
    }
  }

  var empty = document.getElementById('psyops-empty');
  if (empty) empty.style.display = visible === 0 ? '' : 'none';
}

/* --- Sort --- */
function psyopSort(btn, sortBy) {
  var row = btn.parentElement;
  var btns = row.querySelectorAll('.psyops-filter-btn');
  for (var i = 0; i < btns.length; i++) btns[i].classList.remove('pf-active');
  btn.classList.add('pf-active');

  var list = document.getElementById('psyop-list');
  if (!list) return;
  var cards = Array.prototype.slice.call(list.querySelectorAll('.psyop-card'));

  cards.sort(function(a, b) {
    if (sortBy === 'saci') return parseFloat(b.getAttribute('data-saci') || 0) - parseFloat(a.getAttribute('data-saci') || 0);
    if (sortBy === 'legit') return parseFloat(a.getAttribute('data-legit') || 0) - parseFloat(b.getAttribute('data-legit') || 0);
    if (sortBy === 'date') return parseInt(b.getAttribute('data-date') || 0) - parseInt(a.getAttribute('data-date') || 0);
    return 0;
  });

  for (var i = 0; i < cards.length; i++) list.appendChild(cards[i]);
}

/* --- SACI Line Chart Renderer --- */
/* Requires Chart.js loaded before this script */
function psyopRenderLineChart(canvasId, datasets, labels, sugMax, eventMarkers) {
  var canvas = document.getElementById(canvasId);
  if (!canvas) return;
  if (typeof Chart === 'undefined') return;

  var colorMap = {
    red: '#ef4444',
    blue: '#3b82f6',
    cyan: '#06b6d4',
    amber: '#f59e0b',
    green: '#22c55e',
    purple: '#a855f7',
    teal: '#14b8a6'
  };

  var chartDatasets = [];
  for (var i = 0; i < datasets.length; i++) {
    var ds = datasets[i];
    var c = colorMap[ds.color] || ds.color;
    chartDatasets.push({
      label: ds.label,
      data: ds.data,
      borderColor: c,
      backgroundColor: c.replace(')', ',.05)').replace('rgb', 'rgba'),
      fill: true,
      borderWidth: 1.5,
      borderDash: ds.dashed ? [3, 2] : [],
      tension: 0.35,
      pointRadius: 0,
      pointHoverRadius: 3
    });
  }

  var evtPlugin = null;
  if (eventMarkers && eventMarkers.length > 0) {
    evtPlugin = {
      id: 'psyopEvents',
      afterDraw: function(chart) {
        var meta = chart.getDatasetMeta(0);
        if (!meta || !meta.data) return;
        var ctx = chart.ctx;
        var yA = chart.scales.y;
        for (var j = 0; j < eventMarkers.length; j++) {
          var ev = eventMarkers[j];
          if (ev.idx >= meta.data.length) continue;
          var x = meta.data[ev.idx].x;
          ctx.save();
          ctx.beginPath();
          ctx.setLineDash([2, 3]);
          ctx.strokeStyle = (colorMap[ev.color] || ev.color) + '30';
          ctx.lineWidth = 0.5;
          ctx.moveTo(x, yA.top);
          ctx.lineTo(x, yA.bottom);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.arc(x, yA.top + 3, 2, 0, Math.PI * 2);
          ctx.fillStyle = colorMap[ev.color] || ev.color;
          ctx.fill();
          ctx.restore();
        }
      }
    };
  }

  new Chart(canvas, {
    type: 'line',
    data: { labels: labels, datasets: chartDatasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 600, easing: 'easeOutQuart' },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(17,19,24,.95)',
          borderColor: 'rgba(255,255,255,.1)',
          borderWidth: 1,
          titleFont: { family: 'DM Sans', size: 9 },
          bodyFont: { family: 'DM Sans', size: 9 },
          padding: 5,
          cornerRadius: 4
        }
      },
      scales: {
        x: { display: false },
        y: {
          display: true,
          position: 'right',
          grid: { color: 'rgba(255,255,255,.03)', drawBorder: false },
          ticks: { color: 'rgba(255,255,255,.15)', font: { size: 8, family: 'DM Sans' }, maxTicksLimit: 3 },
          suggestedMax: sugMax || undefined,
          beginAtZero: true
        }
      }
    },
    plugins: evtPlugin ? [evtPlugin] : []
  });
}
