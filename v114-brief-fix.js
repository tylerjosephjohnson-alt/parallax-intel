/* ── v114-fe: Brief Tabs + Region Chips Fix ──
   Overrides v6_renderBriefTabs to actually render all 5 panels from brief data.
   Overrides v6_switchBriefRegion to filter top stories by region.
   Added as NEW script block at end of file — no existing code edited.
*/

// ── Helper: format prose with line breaks ──
function v6_formatBriefProse(text) {
  if (!text) return '';
  return text.replace(/\n/g, '<br>').replace(/\\n/g, '<br>');
}

// ── Helper: map chip label to region slug ──
function v6_chipToRegion(label) {
  var map = {
    'north america': 'americas',
    'europe': 'europe',
    'middle east': 'middle-east',
    'east asia': 'asia-pacific',
    'south asia': 'south-asia',
    'africa': 'africa',
    'latin america': 'americas',
    'russia · eurasia': 'russia-fsu',
    'russia eurasia': 'russia-fsu',
    'global · transnational': 'global',
    'global transnational': 'global'
  };
  return map[(label || '').toLowerCase().trim()] || label.toLowerCase().trim();
}

// ── Helper: significance badge color ──
function v6_sigBadge(sig) {
  var s = (sig || '').toLowerCase();
  if (s === 'high' || s === 'critical') return 'v6-w-urgent';
  if (s === 'medium' || s === 'moderate') return 'v6-w-elevated';
  return 'v6-w-routine';
}

// ── OVERRIDE: v6_renderBriefTabs ──
// Returns HTML string with all 5 panels populated from brief data
v6_renderBriefTabs = function(brief) {
  if (!brief) return '';

  // ── Normalize data ──
  var io = brief.intelligence_overview || {};
  var stories = brief.top_stories || brief.stories || [];
  var signals = brief.overnight_signals || [];
  var analystNote = brief.analyst_note || '';
  var contested = brief.contested_numbers_today || [];
  var analysisText = brief.analysis || '';

  // ── Tab bar ──
  var tabs = [
    { label: 'Overview', panel: 'v6-bp-overview' },
    { label: 'Analysis', panel: 'v6-bp-analysis' },
    { label: 'Expected today', panel: 'v6-bp-expected', count: signals.length },
    { label: 'Top stories', panel: 'v6-bp-stories', count: stories.length },
    { label: 'Signals', panel: 'v6-bp-signals' }
  ];
  var tabBar = '<div class="v6-brief-tabs">';
  tabs.forEach(function(t, i) {
    var active = i === 0 ? ' v6-active' : '';
    var badge = t.count ? '<span class="v6-tab-count">' + t.count + '</span>' : '';
    tabBar += '<button class="v6-brief-tab' + active + '" data-panel="' + t.panel + '" onclick="v6_switchBriefTab(this)">' + t.label + badge + '</button>';
  });
  tabBar += '</div>';

  // ── Panel 1: OVERVIEW ──
  var overviewHTML = '';
  if (brief.overview_prose) {
    overviewHTML = '<div class="v6-prose">' + v6_formatBriefProse(brief.overview_prose) + '</div>';
  } else if (io.paragraph_1_situation || io.paragraph_2_connections || io.paragraph_3_what_watch || io.paragraph_4_buried) {
    var parts = [];
    if (io.paragraph_1_situation) parts.push(io.paragraph_1_situation);
    if (io.paragraph_2_connections) parts.push(io.paragraph_2_connections);
    if (io.paragraph_3_what_watch) parts.push(io.paragraph_3_what_watch);
    if (io.paragraph_4_buried) parts.push(io.paragraph_4_buried);
    // Split long text into paragraphs intelligently
    var fullText = parts.join('\n\n');
    var chunks = fullText.split(/\n\n+/);
    var formatted = chunks.map(function(c) { return '<p>' + v6_formatBriefProse(c.trim()) + '</p>'; }).join('');
    overviewHTML = '<div class="v6-prose">' + formatted + '</div>';
  } else {
    overviewHTML = '<p class="v6-empty">Overview will appear when the brief is generated.</p>';
  }

  // ── Panel 2: ANALYSIS ──
  var analysisHTML = '';
  if (analysisText) {
    analysisHTML = '<div class="v6-prose"><h3 class="v6-section-head">ANALYSIS</h3>' + v6_formatBriefProse(analysisText) + '</div>';
  } else if (analystNote) {
    // Use analyst_note as analysis content (it contains deep analysis)
    analysisHTML = '<div class="v6-prose"><h3 class="v6-section-head">ANALYST NOTE</h3>';
    var noteParts = analystNote.split(/\n\n+/);
    noteParts.forEach(function(p) {
      if (p.trim()) analysisHTML += '<p>' + v6_formatBriefProse(p.trim()) + '</p>';
    });
    analysisHTML += '</div>';
    // Add contested numbers if available
    if (contested && contested.length > 0) {
      analysisHTML += '<div class="v6-contested-block"><h3 class="v6-section-head">CONTESTED NUMBERS</h3>';
      contested.forEach(function(cn) {
        analysisHTML += '<div class="v6-contested-item">';
        analysisHTML += '<div class="v6-contested-metric">' + (cn.metric || '') + '</div>';
        analysisHTML += '<div class="v6-contested-sides">';
        analysisHTML += '<div class="v6-contested-a"><span class="v6-contested-label">SIDE A</span> <strong>' + (cn.actor_a || '') + ':</strong> ' + (cn.value_a || '') + '</div>';
        analysisHTML += '<div class="v6-contested-b"><span class="v6-contested-label">SIDE B</span> <strong>' + (cn.actor_b || '') + ':</strong> ' + (cn.value_b || '') + '</div>';
        analysisHTML += '</div>';
        if (cn.why_gap) analysisHTML += '<div class="v6-contested-gap"><span class="v6-contested-label">WHY THE GAP</span> ' + cn.why_gap + '</div>';
        analysisHTML += '</div>';
      });
      analysisHTML += '</div>';
    }
  } else {
    analysisHTML = '<p class="v6-empty">Analysis will appear when the brief is generated.</p>';
  }

  // ── Panel 3: EXPECTED TODAY ──
  var expectedHTML = '';
  if (brief.expected_today && typeof brief.expected_today === 'string') {
    expectedHTML = '<div class="v6-prose">' + v6_formatBriefProse(brief.expected_today) + '</div>';
  } else if (signals.length > 0) {
    // Build expected-today from overnight_signals
    expectedHTML = '<div class="v6-signals-list">';
    signals.forEach(function(s, i) {
      var badge = v6_sigBadge(s.significance);
      expectedHTML += '<div class="v6-signal-card">';
      expectedHTML += '<div class="v6-signal-header">';
      expectedHTML += '<span class="v6-signal-num">' + (i + 1) + '</span>';
      expectedHTML += '<span class="v6-w ' + badge + '"></span>';
      expectedHTML += '</div>';
      expectedHTML += '<div class="v6-signal-body">' + v6_formatBriefProse(s.signal || '') + '</div>';
      expectedHTML += '<div class="v6-signal-source">' + (s.source || '') + '</div>';
      expectedHTML += '</div>';
    });
    expectedHTML += '</div>';
  } else {
    expectedHTML = '<p class="v6-empty">Expected-today predictions will appear when the brief is generated.</p>';
  }

  // ── Panel 4: TOP STORIES ──
  var storiesHTML = '';
  if (stories.length > 0) {
    storiesHTML = '<div class="v6-brief-stories-list">';
    stories.forEach(function(st) {
      var regionSlug = (st.region || 'global').toLowerCase();
      var regionLabel = regionSlug.replace(/-/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
      storiesHTML += '<div class="v6-brief-story-card" data-region="' + regionSlug + '">';
      storiesHTML += '<div class="v6-brief-story-head">';
      storiesHTML += '<span class="v6-brief-story-rank">#' + (st.rank || '') + '</span>';
      storiesHTML += '<span class="v6-brief-story-region">' + regionLabel + '</span>';
      storiesHTML += '</div>';
      storiesHTML += '<h4 class="v6-brief-story-headline">' + (st.headline || '') + '</h4>';
      if (st.paragraph_1_situation) storiesHTML += '<p class="v6-brief-story-para">' + v6_formatBriefProse(st.paragraph_1_situation) + '</p>';
      if (st.paragraph_2_connections) storiesHTML += '<p class="v6-brief-story-para v6-connections">' + v6_formatBriefProse(st.paragraph_2_connections) + '</p>';
      if (st.paragraph_3_watch) storiesHTML += '<p class="v6-brief-story-para v6-watch"><strong>WATCH:</strong> ' + v6_formatBriefProse(st.paragraph_3_watch) + '</p>';
      if (st.significance) storiesHTML += '<p class="v6-brief-story-sig">' + v6_formatBriefProse(st.significance) + '</p>';
      if (st.source) storiesHTML += '<div class="v6-brief-story-source">' + st.source + '</div>';
      storiesHTML += '</div>';
    });
    storiesHTML += '</div>';
  } else {
    storiesHTML = '<p class="v6-empty">Top stories will appear here when stories are generated.</p>';
  }

  // ── Panel 5: SIGNALS ──
  var signalsHTML = '';
  if (signals.length > 0) {
    signalsHTML = '<div class="v6-signals-compact">';
    signals.forEach(function(s, i) {
      var badge = v6_sigBadge(s.significance);
      signalsHTML += '<div class="v6-signal-compact">';
      signalsHTML += '<span class="v6-w ' + badge + '"></span>';
      signalsHTML += '<span class="v6-signal-text">' + (s.signal || '') + '</span>';
      if (s.source) signalsHTML += '<span class="v6-signal-src"> — ' + s.source + '</span>';
      signalsHTML += '</div>';
    });
    signalsHTML += '</div>';
  } else {
    signalsHTML = '<p class="v6-empty">Signals panel will appear when the synthesis pipeline is active.</p>';
  }

  // ── Assemble panels ──
  var html = tabBar;
  html += '<div class="v6-brief-panel v6-active" id="v6-bp-overview">' + overviewHTML + '</div>';
  html += '<div class="v6-brief-panel" id="v6-bp-analysis">' + analysisHTML + '</div>';
  html += '<div class="v6-brief-panel" id="v6-bp-expected">' + expectedHTML + '</div>';
  html += '<div class="v6-brief-panel" id="v6-bp-stories">' + storiesHTML + '</div>';
  html += '<div class="v6-brief-panel" id="v6-bp-signals">' + signalsHTML + '</div>';

  return html;
};

// ── OVERRIDE: v6_switchBriefRegion ──
// Filters top stories by region when a chip is clicked
v6_switchBriefRegion = function(chip) {
  // Toggle active state on chips
  var chips = document.querySelectorAll('.v6-region-chip');
  var wasActive = chip.classList.contains('v6-active');

  // Remove active from all chips
  for (var i = 0; i < chips.length; i++) {
    chips[i].classList.remove('v6-active');
  }

  // If clicking the same chip, deactivate (show all)
  if (wasActive) {
    // Show all stories
    var allCards = document.querySelectorAll('.v6-brief-story-card');
    for (var j = 0; j < allCards.length; j++) {
      allCards[j].style.display = '';
    }
    return;
  }

  // Activate clicked chip
  chip.classList.add('v6-active');

  // Get region slug from chip text
  var chipText = chip.textContent.trim();
  // Remove any badge content (the span inside)
  var span = chip.querySelector('span');
  if (span) chipText = chipText.replace(span.textContent, '').trim();
  var region = v6_chipToRegion(chipText);

  // Filter story cards
  var cards = document.querySelectorAll('.v6-brief-story-card');
  var shown = 0;
  for (var k = 0; k < cards.length; k++) {
    var cardRegion = cards[k].getAttribute('data-region') || '';
    if (cardRegion === region) {
      cards[k].style.display = '';
      shown++;
    } else {
      cards[k].style.display = 'none';
    }
  }

  // Auto-switch to Top Stories tab if not already there
  var storiesTab = document.querySelector('[data-panel="v6-bp-stories"]');
  if (storiesTab && !storiesTab.classList.contains('v6-active')) {
    v6_switchBriefTab(storiesTab);
  }
};
