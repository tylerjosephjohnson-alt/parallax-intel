// Psyops Detection Engine - Data-driven renderer
// Fetches /psyops.json and renders campaign cards dynamically

function psyopsInit() {
  var container = document.getElementById('psyops-campaign-list');
  if (!container) return;
  container.innerHTML = '<div style="color:#888;padding:20px;">Loading scanner data...</div>';
  fetch('/psyops.json')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.scan || !data.scan.campaigns || data.scan.campaigns.length === 0) {
        container.innerHTML = '<div class="placeholder">Detection Engine - Awaiting first scan</div>';
        return;
      }
      renderPsyopsCampaigns(data.scan.campaigns, container);
      var ts = document.getElementById('psyops-scan-timestamp');
      if (ts) ts.textContent = 'Last scan: ' + (data.scan.scan_timestamp || 'Unknown');
    })
    .catch(function(err) {
      container.innerHTML = '<div class="placeholder">Scanner offline</div>';
    });
}

function renderPsyopsCampaigns(campaigns, container) {
  container.innerHTML = '';
  campaigns.forEach(function(c) {
    var card = document.createElement('div');
    card.className = 'psyop-card';
    var confClass = 'psyop-conf-' + (c.confidence || 'suspected');
    var statusClass = 'psyop-status-' + (c.status || 'unknown');
    var saci = c.saci_scores || {};
    var saciOverall = saci.overall ? Math.round(saci.overall * 100) : '--';
    var saciLevel = saci.overall >= 0.7 ? 'high' : saci.overall >= 0.4 ? 'med' : 'low';
    var operators = (c.operators || []).map(function(o) { return o.name; }).join(', ') || 'Unknown';
    var regions = (c.regions_involved || []).join(', ') || c.region || 'Unknown';
    var narratives = c.narratives || {};
    var techniques = c.techniques_detected || [];
    var targets = c.targets || [];

    var html = '<div class="psyop-hdr" onclick="psyopToggleCard(this)">';
    html += '<div class="psyop-hdr-left">';
    html += '<div class="psyop-hdr-info">';
    html += '<span class="psyop-id">' + c.campaign_id + '</span>';
    html += '<span class="psyop-name">' + c.campaign_name + '</span>';
    html += '</div>';
    html += '<div class="psyop-meta">';
    html += '<span class="psyop-operator">' + operators + '</span>';
    html += '<span class="psyop-conf ' + confClass + '">' + (c.confidence || 'Unknown').toUpperCase() + '</span>';
    html += '<span class="psyop-status ' + statusClass + '"><span class="psyop-status-dot"></span>' + (c.status || 'unknown').toUpperCase() + '</span>';
    html += '</div></div>';
    html += '<div class="psyop-hdr-right">';
    html += '<div class="psyop-score"><div class="psyop-score-label">SACI</div>';
    html += '<div class="psyop-score-val psyop-score-' + saciLevel + '">' + saciOverall + '</div></div>';
    html += '<div class="psyop-arrow">&#9660;</div></div></div>';

    html += '<div class="psyop-body">';
    html += '<div class="psyop-summary">' + (c.summary || '') + '</div>';

    html += '<div class="psyop-tabs">';
    html += '<button class="psyop-tab active" onclick="psyopSwitchTab(this,\'overview\')">Overview</button>';
    html += '<button class="psyop-tab" onclick="psyopSwitchTab(this,\'narratives\')">Narratives</button>';
    html += '<button class="psyop-tab" onclick="psyopSwitchTab(this,\'techniques\')">Techniques</button>';
    html += '<button class="psyop-tab" onclick="psyopSwitchTab(this,\'saci\')">SACI</button>';
    html += '</div>';

    html += '<div class="psyop-tab-content" data-tab="overview" style="display:block"><div class="psyop-section">';
    html += '<div class="psyop-field"><span class="psyop-field-label">Type:</span> <span class="psyop-field-value">' + (c.type || '') + '</span></div>';
    html += '<div class="psyop-field"><span class="psyop-field-label">Region:</span> <span class="psyop-field-value">' + regions + '</span></div>';
    html += '<div class="psyop-field"><span class="psyop-field-label">Targets:</span> <span class="psyop-field-value">' + (Array.isArray(targets) ? targets.join(', ') : targets) + '</span></div>';
    html += '<div class="psyop-field"><span class="psyop-field-label">Phase:</span> <span class="psyop-field-value">' + (c.current_phase || '') + '</span></div>';
    html += '<div class="psyop-field"><span class="psyop-field-label">Confidence:</span> <span class="psyop-field-value">' + (c.confidence_reasoning || '') + '</span></div>';
    html += '</div></div>';

    html += '<div class="psyop-tab-content" data-tab="narratives" style="display:none"><div class="psyop-section">';
    html += '<div class="psyop-field"><span class="psyop-field-label">Primary:</span> <span class="psyop-field-value">' + (narratives.primary || 'N/A') + '</span></div>';
    html += '<div class="psyop-field"><span class="psyop-field-label">Counter:</span> <span class="psyop-field-value">' + (narratives.counter || 'N/A') + '</span></div>';
    html += '<div class="psyop-field"><span class="psyop-field-label">Evolution:</span> <span class="psyop-field-value">' + (narratives.evolution || 'N/A') + '</span></div>';
    html += '</div></div>';

    html += '<div class="psyop-tab-content" data-tab="techniques" style="display:none"><div class="psyop-section">';
    techniques.forEach(function(t) { html += '<div class="psyop-field"><span class="psyop-field-value">' + t + '</span></div>'; });
    html += '</div></div>';

    html += '<div class="psyop-tab-content" data-tab="saci" style="display:none"><div class="psyop-section">';
    html += '<div class="psyop-field"><span class="psyop-field-label">Source Integrity:</span> <span class="psyop-field-value">' + (saci.source_integrity ? Math.round(saci.source_integrity * 100) + '%' : '--') + '</span></div>';
    html += '<div class="psyop-field"><span class="psyop-field-label">Actor Alignment:</span> <span class="psyop-field-value">' + (saci.actor_alignment ? Math.round(saci.actor_alignment * 100) + '%' : '--') + '</span></div>';
    html += '<div class="psyop-field"><span class="psyop-field-label">Coordination:</span> <span class="psyop-field-value">' + (saci.coordination_indicators ? Math.round(saci.coordination_indicators * 100) + '%' : '--') + '</span></div>';
    html += '<div class="psyop-field"><span class="psyop-field-label">Info Integrity:</span> <span class="psyop-field-value">' + (saci.information_integrity ? Math.round(saci.information_integrity * 100) + '%' : '--') + '</span></div>';
    html += '<div class="psyop-field"><span class="psyop-field-label">Overall:</span> <span class="psyop-field-value psyop-score-' + saciLevel + '">' + saciOverall + '%</span></div>';
    html += '</div></div>';

    html += '</div>';
    card.innerHTML = html;
    container.appendChild(card);
  });
}

function psyopToggleCard(hdr) {
  hdr.closest('.psyop-card').classList.toggle('expanded');
}

function psyopSwitchTab(btn, tabName) {
  var body = btn.closest('.psyop-body');
  body.querySelectorAll('.psyop-tab').forEach(function(t) { t.classList.remove('active'); });
  btn.classList.add('active');
  body.querySelectorAll('.psyop-tab-content').forEach(function(tc) {
    tc.style.display = tc.getAttribute('data-tab') === tabName ? 'block' : 'none';
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', psyopsInit);
} else {
  psyopsInit();
}
