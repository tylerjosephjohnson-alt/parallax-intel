/* predictions-engine.js — Vantage Predictions Intelligence Forecasting
   Renders predictions from /predictions.json
   Auto-bootstraps on load */

var _predData = null;

function predProbClass(p) { return p >= 65 ? 'high' : p >= 35 ? 'med' : 'low'; }
function predProbWord(p) {
  if (p >= 85) return 'VERY LIKELY';
  if (p >= 65) return 'LIKELY';
  if (p >= 45) return 'POSSIBLE';
  if (p >= 25) return 'UNCERTAIN';
  return 'UNLIKELY';
}
function predEsc(s) { return (s||'').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function predFmt(s) { return (s||'').replace(/\n/g,'<br>').replace(/\\n/g,'<br>'); }
function predCatClass(c) {
  var m = {'economic':'cat-economic','military':'cat-military','political':'cat-political',
    'humanitarian':'cat-humanitarian','cyber':'cat-cyber','corporate':'cat-corporate',
    'financial':'cat-financial','technology':'cat-technology'};
  return m[(c||'').toLowerCase()] || 'cat-economic';
}

function predRenderCard(p) {
  var prob = p.probability || 0;
  var status = (p.status||'active').toLowerCase();
  var isConfirmed = status === 'confirmed';
  var cls = predProbClass(prob);
  var h = '<div class="p-card ' + status + '" data-status="' + status + '" data-cat="' + predEsc(p.category||'') + '" data-region="' + predEsc(p.region||'') + '" onclick="predToggle(this)">';
  h += '<div class="p-top"><div class="p-prob">';
  if (isConfirmed) {
    h += '<div class="p-prob-num" style="color:#3ddc84">✓</div><div class="p-prob-label">Confirmed</div>';
  } else {
    h += '<div class="p-prob-num ' + cls + '">' + prob + '%</div>';
    h += '<div class="p-prob-label">' + predProbWord(prob) + '</div>';
    h += '<div class="p-prob-bar"><div class="p-prob-fill" style="width:' + prob + '%;background:' + (cls==='high'?'#e05555':cls==='med'?'#d4a84b':'#3ddc84') + '"></div></div>';
    if (p.confidence_band) h += '<div class="p-prob-band">' + predEsc(p.confidence_band) + '</div>';
  }
  h += '</div><div class="p-info">';
  h += '<div class="p-headline">' + predFmt(p.headline||'') + '</div>';
  h += '<div class="p-meta-row">';
  if (p.regions) { (Array.isArray(p.regions)?p.regions:[p.regions]).forEach(function(r){h += '<span class="p-tag region">' + predEsc(r) + '</span>';}); }
  else if (p.region) { h += '<span class="p-tag region">' + predEsc(p.region) + '</span>'; }
  if (p.category) h += '<span class="p-tag ' + predCatClass(p.category) + '">' + predEsc(p.category) + '</span>';
  h += '<span class="p-tag status-' + status + '">' + predEsc(status.charAt(0).toUpperCase()+status.slice(1)) + '</span>';
  if (p.updated) h += '<span class="p-updated">' + predEsc(p.updated) + '</span>';
  h += '</div></div><div class="p-expand-icon">▸</div></div>';

  // Body
  h += '<div class="p-body">';

  // Logic chain
  if (p.logic_chain && p.logic_chain.length > 0) {
    h += '<div class="p-section-label">Logic Chain</div><div class="p-logic">';
    p.logic_chain.forEach(function(step, i) {
      var arrow = (i === p.logic_chain.length - 1) ? '∴' : (i+1) + '→';
      h += '<div class="p-logic-step"><span class="p-logic-arrow">' + arrow + '</span><span class="p-logic-text">' + predFmt(step) + '</span></div>';
    });
    h += '</div>';
  }

  // Probability history
  if (p.probability_history && p.probability_history.length > 0) {
    h += '<div class="p-section-label">Probability History</div><div class="p-history">';
    p.probability_history.forEach(function(ph, i) {
      if (i > 0) h += '<span class="p-hist-arrow">→</span>';
      var valClass = i > 0 ? (ph.value > p.probability_history[i-1].value ? 'up' : ph.value < p.probability_history[i-1].value ? 'down' : 'same') : 'same';
      h += '<div class="p-hist-point"><span class="p-hist-date">' + predEsc(ph.date) + '</span><span class="p-hist-val ' + valClass + '">' + ph.value + '%</span>';
      if (ph.reason) h += '<span class="p-hist-reason">— ' + predEsc(ph.reason) + '</span>';
      h += '</div>';
    });
    h += '</div>';
  }

  // Accelerators / Decelerators
  if ((p.accelerators && p.accelerators.length > 0) || (p.decelerators && p.decelerators.length > 0)) {
    h += '<div class="p-section-label">What Changes This Probability</div><div class="p-accel-grid">';
    if (p.accelerators && p.accelerators.length > 0) {
      h += '<div class="p-accel-box more"><div class="p-accel-title more">▲ Makes More Likely</div>';
      p.accelerators.forEach(function(a) {
        h += '<div class="p-accel-item"><span class="p-accel-icon more">▲</span><span class="p-accel-text">' + predFmt(a.event||a) + '</span>';
        if (a.impact) h += '<span class="p-accel-impact more">' + predEsc(a.impact) + '</span>';
        h += '</div>';
      });
      h += '</div>';
    }
    if (p.decelerators && p.decelerators.length > 0) {
      h += '<div class="p-accel-box less"><div class="p-accel-title less">▼ Makes Less Likely</div>';
      p.decelerators.forEach(function(d) {
        h += '<div class="p-accel-item"><span class="p-accel-icon less">▼</span><span class="p-accel-text">' + predFmt(d.event||d) + '</span>';
        if (d.impact) h += '<span class="p-accel-impact less">' + predEsc(d.impact) + '</span>';
        h += '</div>';
      });
      h += '</div>';
    }
    h += '</div>';
  }

  // Historical precedent
  if (p.historical_precedent) {
    h += '<div class="p-section-label">Historical Precedent</div>';
    h += '<div class="p-block precedent"><div class="p-block-label precedent">Base Rate Analysis</div>';
    h += '<div class="p-block-text">' + predFmt(p.historical_precedent) + '</div></div>';
  }

  // Competing hypothesis
  if (p.competing_hypothesis) {
    h += '<div class="p-section-label">Strongest Counter-Argument</div>';
    h += '<div class="p-block counter"><div class="p-block-label counter">Why This Might Not Happen</div>';
    h += '<div class="p-block-text">' + predFmt(p.competing_hypothesis) + '</div></div>';
  }

  // Falsification criteria
  if (p.falsification) {
    h += '<div class="p-section-label">What Would Prove This Wrong</div>';
    h += '<div class="p-block falsify"><div class="p-block-label falsify">Falsification Criteria</div>';
    h += '<div class="p-block-text">' + predFmt(p.falsification) + '</div></div>';
  }

  // Connected predictions
  if (p.connected_predictions) {
    h += '<div class="p-section-label">Connected Predictions</div>';
    h += '<div class="p-block connected"><div class="p-block-label connected">If This Fires, It Affects</div>';
    h += '<div class="p-block-text">' + predFmt(p.connected_predictions) + '</div></div>';
  }

  // Key indicators
  if (p.indicators && p.indicators.length > 0) {
    h += '<div class="p-section-label">Key Indicators</div>';
    p.indicators.forEach(function(ind) {
      var statusCls = (ind.status||'watching').toLowerCase();
      h += '<div class="p-ind-item"><span class="p-ind-icon">◉</span><span class="p-ind-text">' + predFmt(ind.text||ind) + '</span>';
      if (ind.status) h += '<span class="p-ind-status ' + statusCls + '">' + predEsc(ind.status.toUpperCase()) + '</span>';
      h += '</div>';
    });
  }

  // Outcome (for confirmed)
  if (p.outcome) {
    h += '<div class="p-section-label">Outcome vs Prediction</div><div class="p-logic">';
    (Array.isArray(p.outcome) ? p.outcome : [p.outcome]).forEach(function(o) {
      h += '<div class="p-logic-step"><span class="p-logic-arrow">✓</span><span class="p-logic-text">' + predFmt(o) + '</span></div>';
    });
    h += '</div>';
  }

  if (p.sources) h += '<div class="p-src">' + predEsc(p.sources) + '</div>';
  h += '</div></div>';
  return h;
}

function predRender() {
  var container = document.getElementById('view-predictions');
  if (!container || !_predData) return;

  var h = '<div class="pred-head"><h2>Predictions <span>— Intelligence Forecasting</span></h2>';
  h += '<div class="pred-sub">Evidence-based forecasts with probability tracking, accelerators, and historical validation</div>';
  h += '<div class="pred-ts">Last updated: ' + predEsc(_predData.generated_at||'') + ' · Cross-referenced with daily brief data</div></div>';

  // Scorecard
  var sc = _predData.scorecard || {};
  h += '<div class="scorecard">';
  h += '<div class="sc-item"><div class="sc-num blue">' + (sc.active||0) + '</div><div class="sc-label">Active</div></div>';
  h += '<div class="sc-item"><div class="sc-num green">' + (sc.confirmed||0) + '</div><div class="sc-label">Confirmed</div></div>';
  h += '<div class="sc-item"><div class="sc-num amber">' + (sc.evolving||0) + '</div><div class="sc-label">Evolving</div></div>';
  h += '<div class="sc-item"><div class="sc-num red">' + (sc.invalidated||0) + '</div><div class="sc-label">Invalidated</div></div>';
  h += '<div class="sc-item"><div class="sc-num cyan">' + (sc.accuracy_rate||'--') + '</div><div class="sc-label">Accuracy Rate</div></div>';
  h += '</div>';

  // Filters
  h += '<div class="pred-filter-row"><span class="pred-filter-label">Status:</span>';
  h += '<button class="pf-chip active" onclick="predFilter(\'all\',this)">All</button>';
  h += '<button class="pf-chip" onclick="predFilter(\'active\',this)">Active</button>';
  h += '<button class="pf-chip" onclick="predFilter(\'evolving\',this)">Evolving</button>';
  h += '<button class="pf-chip" onclick="predFilter(\'confirmed\',this)">Confirmed</button>';
  h += '<div class="pf-divider"></div><span class="pred-filter-label">Type:</span>';
  var cats = ['Economic','Military','Political','Humanitarian','Cyber','Corporate','Technology','Financial'];
  cats.forEach(function(c){ h += '<button class="pf-chip" onclick="predFilter(\'' + c.toLowerCase() + '\',this)">' + c + '</button>'; });
  h += '</div>';

  // Group by timeframe
  var timeframes = _predData.timeframes || [];
  timeframes.forEach(function(tf) {
    h += '<div class="tf-header">' + predEsc(tf.label||'') + '</div>';
    (tf.predictions||[]).forEach(function(p) { h += predRenderCard(p); });
  });

  container.innerHTML = h;
}

function predToggle(card) {
  if (event.target.closest('.p-body')) return;
  card.classList.toggle('open');
}

function predFilter(cat, btn) {
  var container = document.getElementById('view-predictions');
  container.querySelectorAll('.pf-chip').forEach(function(c){c.classList.remove('active');});
  btn.classList.add('active');
  var cards = container.querySelectorAll('.p-card');
  if (cat === 'all') { cards.forEach(function(c){c.style.display='';}); return; }
  cards.forEach(function(c) {
    var status = c.getAttribute('data-status')||'';
    var cardCat = (c.getAttribute('data-cat')||'').toLowerCase();
    var region = (c.getAttribute('data-region')||'').toLowerCase();
    var match = (status===cat)||(cardCat===cat)||(region.indexOf(cat)>-1);
    c.style.display = match ? '' : 'none';
  });
}

// Bootstrap
(function() {
  var link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = '/predictions-engine.css';
  document.head.appendChild(link);
  fetch('/predictions.json').then(function(r) {
    if (!r.ok) return null;
    return r.json();
  }).then(function(data) {
    if (data && data.timeframes) {
      _predData = data;
      predRender();
    }
  }).catch(function(e) {
    console.log('Predictions: no data yet');
  });
})();
