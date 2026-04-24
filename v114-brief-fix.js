/* ── v114-fe: Brief Tabs Styling ── */
.v6-section-head {
  font-size: 0.7rem;
  letter-spacing: 0.12em;
  color: #8a8f98;
  margin: 0 0 0.75rem 0;
  padding-bottom: 0.4rem;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}

/* Contested numbers */
.v6-contested-block { margin-top: 1.5rem; }
.v6-contested-item {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 6px;
  padding: 0.9rem;
  margin-bottom: 0.75rem;
}
.v6-contested-metric {
  font-weight: 600;
  font-size: 0.85rem;
  color: #e0e0e0;
  margin-bottom: 0.6rem;
}
.v6-contested-sides { display: flex; flex-direction: column; gap: 0.5rem; }
.v6-contested-a, .v6-contested-b {
  font-size: 0.8rem;
  color: #b0b4bc;
  line-height: 1.5;
}
.v6-contested-label {
  display: inline-block;
  font-size: 0.65rem;
  letter-spacing: 0.08em;
  color: #8a8f98;
  background: rgba(255,255,255,0.05);
  padding: 1px 5px;
  border-radius: 3px;
  margin-right: 0.3rem;
  vertical-align: middle;
}
.v6-contested-gap {
  margin-top: 0.5rem;
  font-size: 0.78rem;
  color: #9ba0a8;
  line-height: 1.5;
  padding-top: 0.5rem;
  border-top: 1px dashed rgba(255,255,255,0.06);
}

/* Signal cards (Expected Today panel) */
.v6-signals-list { display: flex; flex-direction: column; gap: 0.75rem; }
.v6-signal-card {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 6px;
  padding: 0.8rem 0.9rem;
}
.v6-signal-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}
.v6-signal-num {
  font-size: 0.7rem;
  font-weight: 700;
  color: #8a8f98;
  min-width: 1.2rem;
}
.v6-signal-body {
  font-size: 0.82rem;
  color: #c8ccd4;
  line-height: 1.55;
}
.v6-signal-source {
  font-size: 0.7rem;
  color: #6b7280;
  margin-top: 0.4rem;
}

/* Top stories cards */
.v6-brief-stories-list { display: flex; flex-direction: column; gap: 1rem; }
.v6-brief-story-card {
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 6px;
  padding: 1rem;
}
.v6-brief-story-head {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 0.5rem;
}
.v6-brief-story-rank {
  font-size: 0.65rem;
  font-weight: 700;
  color: #8a8f98;
  letter-spacing: 0.05em;
}
.v6-brief-story-region {
  font-size: 0.6rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #6b7280;
  background: rgba(255,255,255,0.05);
  padding: 2px 6px;
  border-radius: 3px;
}
.v6-brief-story-headline {
  font-size: 0.92rem;
  font-weight: 600;
  color: #e8eaed;
  margin: 0 0 0.6rem 0;
  line-height: 1.35;
}
.v6-brief-story-para {
  font-size: 0.8rem;
  color: #b0b4bc;
  line-height: 1.55;
  margin: 0 0 0.5rem 0;
}
.v6-brief-story-para.v6-connections {
  color: #9ba8b8;
  border-left: 2px solid rgba(100,140,200,0.3);
  padding-left: 0.7rem;
}
.v6-brief-story-para.v6-watch {
  color: #a0b0c0;
}
.v6-brief-story-sig {
  font-size: 0.75rem;
  color: #8a9aaa;
  font-style: italic;
  margin: 0.3rem 0 0.3rem 0;
  line-height: 1.5;
}
.v6-brief-story-source {
  font-size: 0.68rem;
  color: #5a6370;
  margin-top: 0.4rem;
}

/* Signals compact (Signals panel) */
.v6-signals-compact { display: flex; flex-direction: column; gap: 0.6rem; }
.v6-signal-compact {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  font-size: 0.8rem;
  color: #b0b4bc;
  line-height: 1.5;
}
.v6-signal-compact .v6-w { flex-shrink: 0; margin-top: 0.3rem; }
.v6-signal-text { flex: 1; }
.v6-signal-src { color: #5a6370; font-size: 0.7rem; white-space: nowrap; }

/* Region chip active state */
.v6-region-chip.v6-active {
  background: rgba(100,160,255,0.15) !important;
  border-color: rgba(100,160,255,0.4) !important;
  color: #7cb3ff !important;
}

/* Tab count badge */
.v6-tab-count {
  font-size: 0.6rem;
  background: rgba(255,255,255,0.1);
  padding: 1px 5px;
  border-radius: 8px;
  margin-left: 0.3rem;
  vertical-align: middle;
}
