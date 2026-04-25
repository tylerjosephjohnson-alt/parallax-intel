/* atlas-engine.js — Vantage Atlas Economic Intelligence
   Renders region and country economic profiles from /atlas.json
   Auto-bootstraps on load */

// ── STATE ──
var _atlasData = null;
var _atlasView = 'regions'; // 'regions', 'region', 'country'
var _atlasRegion = null;
var _atlasCountry = null;

// ── HELPERS ──
function atlasScoreClass(score) {
  if (score >= 60) return 'good';
  if (score >= 33) return 'caution';
  return 'stress';
}
function atlasScoreWord(score) {
  if (score >= 80) return 'STABLE';
  if (score >= 60) return 'MODERATE';
  if (score >= 45) return 'CAUTION';
  if (score >= 33) return 'ELEVATED STRESS';
  if (score >= 20) return 'SEVERE STRESS';
  return 'NEAR CRISIS';
}
function atlasDirClass(dir) {
  var d = (dir || '').toLowerCase();
  if (d.indexOf('up-bad') > -1 || d === 'ub') return 'ub';
  if (d.indexOf('up-good') > -1 || d === 'ug') return 'ug';
  if (d.indexOf('down-bad') > -1 || d === 'db') return 'db';
  if (d.indexOf('down-good') > -1 || d === 'dg') return 'dg';
  if (d.indexOf('critical') > -1 || d === 'cr') return 'cr';
  if (d.indexOf('stable') > -1 || d === 'st') return 'st';
  return 'st';
}
function atlasStatusClass(status) {
  var s = (status || '').toLowerCase();
  if (s === 'critical' || s === 'stress') return 'stress';
  if (s === 'caution' || s === 'declining') return 'caution';
  if (s === 'good' || s === 'improving' || s === 'stable') return 'good';
  return 'caution';
}
function atlasEsc(s) { return (s || '').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function atlasFmt(s) { return (s || '').replace(/\n/g, '<br>').replace(/\\n/g, '<br>'); }

// ── HEALTH SCORE BOX ──
function atlasRenderHealth(data) {
  var sc = data.health_score || 0;
  var cls = atlasScoreClass(sc);
  var word = atlasScoreWord(sc);
  var factors = data.health_factors || [];
  var h = '<div class="health-box"><div class="health-top">';
  h += '<div class="h-score ' + cls + '">' + sc + '</div>';
  h += '<div><div class="h-label">Economic Health</div><div class="h-word ' + cls + '">' + word + '</div></div>';
  h += '</div>';
  h += '<div class="h-scale"><div class="h-marker" style="left:' + Math.min(sc, 98) + '%"></div></div>';
  h += '<div class="h-ranges"><span>0 Crisis</span><span>33 Stress</span><span>60 Caution</span><span>100 Stable</span></div>';
  if (factors.length > 0) {
    h += '<button class="h-toggle" onclick="this.nextElementSibling.classList.toggle(\'hidden\')">&#9656; What drives this score?</button>';
    h += '<div class="h-factors hidden">';
    factors.forEach(function(f) {
      var barColor = f.value >= 60 ? '#3ddc84' : f.value >= 33 ? '#d4a84b' : '#e05555';
      h += '<div class="h-factor"><span class="h-factor-name">' + atlasEsc(f.name) + '</span>';
      h += '<div class="h-factor-bar-bg"><div class="h-factor-bar" style="width:' + f.value + '%;background:' + barColor + '"></div></div>';
      h += '<span class="h-factor-val">' + f.value + '</span></div>';
    });
    h += '</div>';
  }
  h += '</div>';
  return h;
}

// ── METRIC TABLE ──
function atlasRenderMetricTable(metrics, cat) {
  if (!metrics || metrics.length === 0) return '';
  var h = '<table class="m-table"><thead><tr><th>Metric</th><th>Current</th><th>Baseline</th><th>Direction</th><th></th></tr></thead><tbody>';
  metrics.forEach(function(m) {
    var dirCls = atlasDirClass(m.direction_class || '');
    var statusCls = atlasStatusClass(m.status || '');
    var valColor = statusCls === 'stress' ? 'color:#e05555' : statusCls === 'caution' ? 'color:#d4a84b' : '';
    h += '<tr class="m-row" data-cat="' + (m.category || cat) + '" data-status="' + (m.status || '') + '" onclick="atlasToggleExpand(this)">';
    h += '<td class="m-name">' + atlasEsc(m.name) + '</td>';
    h += '<td style="' + valColor + '">' + atlasEsc(m.current) + '</td>';
    h += '<td><span class="m-base-label">' + atlasEsc(m.baseline_label || '') + '</span><span class="m-base">' + atlasEsc(m.baseline) + '</span></td>';
    h += '<td><span class="m-dir ' + dirCls + '">' + atlasEsc(m.direction) + '</span></td>';
    h += '<td><span class="m-status ' + statusCls + '"></span></td>';
    h += '</tr>';
    // Expand row
    h += '<tr class="m-expand" data-cat="' + (m.category || cat) + '" data-status="' + (m.status || '') + '"><td colspan="5"><div class="m-expand-inner">';
    if (m.why) h += '<div class="m-why"><b>Why</b>' + atlasFmt(m.why) + '</div>';
    if (m.cascade) {
      h += '<div class="m-cascade"><div class="m-cascade-label">If This Changes &rarr;</div><p>' + atlasFmt(m.cascade) + '</p></div>';
    }
    if (m.source) h += '<div class="m-src">' + atlasEsc(m.source) + '</div>';
    h += '</div></td></tr>';
  });
  h += '</tbody></table>';
  return h;
}

// ── CASCADE SECTION ──
function atlasRenderCascades(cascades) {
  if (!cascades || cascades.length === 0) return '';
  var h = '<div class="casc-section"><div class="casc-title">Cascading Effects &mdash; Critical Watchpoints</div>';
  cascades.forEach(function(c) {
    h += '<div class="casc-item"><div class="casc-if">IF &rarr;</div><div class="casc-then">' + atlasFmt(c) + '</div></div>';
  });
  h += '</div>';
  return h;
}

// ── REGION VIEW ──
function atlasRenderRegion(region) {
  var h = '<div class="a-crumb"><span onclick="atlasShowRegions()">Atlas</span> &rarr; ' + atlasEsc(region.name) + '</div>';
  // Header
  h += '<div class="c-header"><div class="c-header-info"><div class="c-title">' + atlasEsc(region.name) + ' &mdash; Regional Economic Profile</div><div class="c-meta">';
  (region.meta || []).forEach(function(m) {
    h += '<div class="c-meta-item"><b>' + atlasEsc(m.label) + '</b>' + atlasEsc(m.value) + '</div>';
  });
  h += '</div></div>' + atlasRenderHealth(region) + '</div>';
  // Assessment
  if (region.assessment) {
    h += '<div class="assess"><div class="assess-label">Regional Assessment</div><div class="assess-text">' + atlasFmt(region.assessment) + '</div></div>';
  }
  // Regional metrics
  if (region.metrics && region.metrics.length > 0) {
    h += '<div class="m-section">Regional Aggregate Indicators</div>';
    h += atlasRenderMetricTable(region.metrics, 'region');
  }
  // Countries
  if (region.countries && region.countries.length > 0) {
    h += '<div class="m-section">Countries in Region</div><div class="r-grid">';
    region.countries.forEach(function(c) {
      var cls = atlasScoreClass(c.health_score || 50);
      h += '<div class="r-chip" onclick="atlasShowCountry(\'' + atlasEsc(c.id || c.name) + '\')">';
      h += '<div class="r-chip-name">' + atlasEsc(c.name) + '</div>';
      h += '<div class="r-chip-row"><span class="r-chip-score ' + cls + '">' + (c.health_score || '?') + '</span>';
      h += '<span class="r-chip-gdp">' + atlasEsc(c.summary || '') + '</span></div></div>';
    });
    h += '</div>';
  }
  // Cascading effects
  h += atlasRenderCascades(region.cascading_effects);
  return h;
}

// ── COUNTRY VIEW ──
function atlasRenderCountry(country, regionName) {
  var h = '<div class="a-crumb"><span onclick="atlasShowRegions()">Atlas</span> &rarr; <span onclick="atlasShowRegionByName(\'' + atlasEsc(regionName) + '\')">' + atlasEsc(regionName) + '</span> &rarr; ' + atlasEsc(country.name) + '</div>';
  // Header
  h += '<div class="c-header"><div class="c-header-info"><div class="c-title">' + atlasEsc(country.name) + ' &mdash; Economic Profile</div><div class="c-meta">';
  (country.meta || []).forEach(function(m) {
    h += '<div class="c-meta-item"><b>' + atlasEsc(m.label) + '</b>' + atlasEsc(m.value) + '</div>';
  });
  h += '</div></div>' + atlasRenderHealth(country) + '</div>';
  // Assessment
  if (country.assessment) {
    h += '<div class="assess"><div class="assess-label">Country Assessment</div><div class="assess-text">' + atlasFmt(country.assessment) + '</div></div>';
  }
  // Filters
  h += '<div class="filter-row"><span class="filter-label">Show:</span>';
  h += '<button class="f-chip active" onclick="atlasFilter(\'all\',this)">All</button>';
  h += '<button class="f-chip" onclick="atlasFilter(\'core\',this)">Core Economic</button>';
  h += '<button class="f-chip" onclick="atlasFilter(\'market\',this)">Market</button>';
  h += '<button class="f-chip" onclick="atlasFilter(\'structural\',this)">Structural</button>';
  h += '<button class="f-chip" onclick="atlasFilter(\'vulnerability\',this)">Vulnerability</button>';
  h += '<button class="f-chip" onclick="atlasFilter(\'geopolitical\',this)">Geopolitical</button>';
  h += '<div class="f-divider"></div>';
  h += '<button class="f-chip crit" onclick="atlasFilter(\'critical\',this)">&#9888; Critical Only</button>';
  h += '<button class="f-chip" onclick="atlasFilter(\'declining\',this)">Declining</button>';
  h += '</div>';
  // Metric sections
  var sections = country.sections || [];
  sections.forEach(function(sec) {
    h += '<div class="m-section" data-cat="' + (sec.category || '') + '">' + atlasEsc(sec.title) + '</div>';
    h += atlasRenderMetricTable(sec.metrics, sec.category);
  });
  // Cascading effects
  h += atlasRenderCascades(country.cascading_effects);
  return h;
}

// ── REGIONS LIST VIEW ──
function atlasRenderRegionsList(data) {
  var h = '<div class="a-crumb">Atlas &mdash; Select a region</div>';
  h += '<div class="r-grid">';
  (data.regions || []).forEach(function(r) {
    var cls = atlasScoreClass(r.health_score || 50);
    h += '<div class="r-chip" onclick="atlasShowRegionByName(\'' + atlasEsc(r.name) + '\')">';
    h += '<div class="r-chip-name">' + atlasEsc(r.name) + '</div>';
    h += '<div class="r-chip-row"><span class="r-chip-score ' + cls + '">' + (r.health_score || '?') + '</span>';
    h += '<span class="r-chip-gdp">' + atlasEsc(r.summary || '') + '</span></div></div>';
  });
  h += '</div>';
  return h;
}

// ── NAVIGATION ──
function atlasShowRegions() {
  _atlasView = 'regions';
  _atlasRegion = null;
  _atlasCountry = null;
  atlasRender();
}
function atlasShowRegionByName(name) {
  if (!_atlasData) return;
  var region = (_atlasData.regions || []).find(function(r) { return r.name === name; });
  if (region) {
    _atlasView = 'region';
    _atlasRegion = region;
    _atlasCountry = null;
    atlasRender();
  }
}
function atlasShowCountry(id) {
  if (!_atlasRegion) return;
  var country = (_atlasRegion.countries || []).find(function(c) { return (c.id || c.name) === id; });
  if (country) {
    _atlasView = 'country';
    _atlasCountry = country;
    atlasRender();
  }
}

// ── EXPAND/FILTER ──
function atlasToggleExpand(row) {
  var next = row.nextElementSibling;
  if (next && next.classList.contains('m-expand')) next.classList.toggle('open');
}
function atlasFilter(cat, btn) {
  var container = document.getElementById('view-atlas');
  container.querySelectorAll('.f-chip').forEach(function(c) { c.classList.remove('active'); });
  btn.classList.add('active');
  var rows = container.querySelectorAll('.m-row, .m-expand');
  var sections = container.querySelectorAll('.m-section');
  if (cat === 'all') {
    rows.forEach(function(r) { r.style.display = ''; });
    sections.forEach(function(s) { s.style.display = ''; });
    return;
  }
  if (cat === 'critical' || cat === 'declining' || cat === 'improving') {
    sections.forEach(function(s) { s.style.display = ''; });
    rows.forEach(function(r) {
      var status = r.getAttribute('data-status');
      if (!status) { r.style.display = 'none'; return; }
      if (cat === 'critical' && status === 'critical') r.style.display = '';
      else if (cat === 'declining' && (status === 'declining' || status === 'critical')) r.style.display = '';
      else if (cat === 'improving' && status === 'improving') r.style.display = '';
      else r.style.display = 'none';
    });
  } else {
    rows.forEach(function(r) {
      var rCat = r.getAttribute('data-cat');
      if (!rCat) { r.style.display = 'none'; return; }
      r.style.display = (rCat === cat) ? '' : 'none';
    });
    sections.forEach(function(s) {
      var sCat = s.getAttribute('data-cat');
      if (!sCat) return;
      if (cat === 'vulnerability') s.style.display = (sCat === 'vulnerability' || sCat === 'structural') ? '' : 'none';
      else s.style.display = (sCat === cat) ? '' : 'none';
    });
  }
}

// ── MAIN RENDER ──
function atlasRender() {
  var container = document.getElementById('view-atlas');
  if (!container || !_atlasData) return;
  var h = '<div class="atlas-head"><div><h2>Atlas <span>&mdash; Economic Intelligence</span></h2>';
  h += '<div class="atlas-ts">Enriched ' + atlasEsc(_atlasData.generated_at || '') + ' &middot; ' + atlasEsc(_atlasData.sources || 'IMF, World Bank, Trading Economics') + '</div>';
  h += '</div></div>';
  // Nav buttons
  h += '<div class="a-nav">';
  (_atlasData.regions || []).forEach(function(r) {
    var active = (_atlasRegion && _atlasRegion.name === r.name) ? ' active' : '';
    h += '<button class="a-nav-btn' + active + '" onclick="atlasShowRegionByName(\'' + atlasEsc(r.name) + '\')">' + atlasEsc(r.name) + '</button>';
  });
  h += '</div>';
  // View content
  if (_atlasView === 'country' && _atlasCountry && _atlasRegion) {
    h += atlasRenderCountry(_atlasCountry, _atlasRegion.name);
  } else if (_atlasView === 'region' && _atlasRegion) {
    h += atlasRenderRegion(_atlasRegion);
  } else {
    h += atlasRenderRegionsList(_atlasData);
  }
  container.innerHTML = h;
  container.scrollTop = 0;
}

// ── BOOTSTRAP ──
(function() {
  // Load CSS
  var link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = '/atlas-engine.css';
  document.head.appendChild(link);
  // Load data
  fetch('/atlas.json').then(function(r) {
    if (!r.ok) return null;
    return r.json();
  }).then(function(data) {
    if (data && data.regions) {
      _atlasData = data;
      atlasRender();
    }
  }).catch(function(e) {
    console.log('Atlas: no data yet (atlas.json not generated)');
  });
})();
