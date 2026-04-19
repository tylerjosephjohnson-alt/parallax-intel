# Vantage — Full Context for Next Claude Session

**IMPORTANT:** Read this entire file before doing anything. It contains everything you need to pick up the project cleanly. Follow its instructions literally.

**Product is called Vantage. Repo/code still says "parallax" — rebrand is branding-only so far, filenames and routes unchanged.**

---

## Quick reference

- **Live URL:** https://web-production-532874.up.railway.app
- **App login password:** `parallax2026`
- **GitHub repo:** github.com/tylerjosephjohnson-alt/parallax-intel
- **Railway project ID:** dfd3cd10-374d-4db1-9ba6-9672e0e4260a
- **Railway service ID:** 3442072e-951d-4566-b7da-6effd4f831d1
- **Railway environment ID:** 60b7e4f3-67a0-4de7-9bfb-fac5da3cf1c0
- **Anthropic model used:** claude-sonnet-4-6
- **Planned public domain:** vantage.news (not purchased yet — verify availability before user buys)
- **Tyler's workflow:** browser-only, beginner coder, no terminal, no local dev env
- **Edit pattern:** Claude uses Chrome browser tools on GitHub web editor via CM6 dispatch (`document.querySelector('.cm-content').cmTile.view.dispatch(...)`)

---

## Current state (end of v36 session, 2026-04-19)

### What works
- Backend brief generation — returns valid 44K-char JSON with all 13 fields
- New clean Vantage UI live at `/` — loads in both dark and light modes, nav swaps views, theme toggle works, zero JS errors on current page
- `/debug-brief` endpoint for inspecting brief generation failures
- Scraper running at 720-min interval (~$0.50/day cost target, 2x/day cadence)
- Backend routes: `/` `/brief.json` `/stories.json` `/story-history.json` `/trigger-brief` (GET) `/debug-brief` `/research` (POST)

### What's broken / flagged
- **`/brief.json` currently 404** — Railway ephemeral filesystem wiped on v15 redeploy. Fresh brief was triggered end of session but not yet complete. Will auto-recover within ~5 min of trigger, or next scheduled scrape.
- **`/stories.json` near-empty (246 bytes)** — same reason. Repopulates on next scrape run (up to 7 hours).
- **`parallax_37.html` and `parallax-FIXED-v2-legacy.html` still in repo** — preserved intentionally as reference material, not served anywhere. Leave them alone.

### Version history (commits shipped so far)
- **v8** (8ea5608): scrape interval 30→60 min, robust JSON repair pass
- **v9**: `json.loads(strict=False)` — didn't help
- **v10**: added `/debug-brief` endpoint
- **v11**: brief `max_tokens` 8000→16000 (line 2823 main.py) — **this was the actual fix** for brief failures. Root cause was Claude response truncation, not malformed JSON.
- **v12**: scrape interval 60→420 min (line 60 main.py), cost cut to ~$1/day
- **v13**: rename `parallax-FIXED-v2.html` → `parallax-FIXED-v2-legacy.html` (preserve, not delete)
- **v14**: add clean `parallax.html` (16KB, 330 lines, Vantage design)
- **v15**: line 3175 main.py changed to `send_file("parallax.html")`
- **v17**: brief API timeout 300→600 sec (line 2841 main.py) — fix read timeout on slow Anthropic responses
- **v18**: parallax.html updated to render intelligence_overview object structure (4 labeled paragraphs) and top_stories with real field names (headline, paragraph_1-4, contested_claim, significance, source, flags)
- **v19**: scrape interval 420→720 min (line 60 main.py), cost target reduced to ~$0.50/day, 2x/day cadence for testing phase
- **v20** (6530179): CONTEXT.md — added v17-v19 entries, reduced stability watch 100→30 days, updated interval/cost refs
- **v21** (be3d550): fixed scraper f-string `ValueError` at main.py:2664 — single `{...}` → `{{...}}` (root cause of earlier Story 1 generation crashes)
- **v22** (7b5ca75): filter bar + search on All Stories view, Settings page with theme toggle relocated there, 6-column sidebar nav with groups (DAILY / ANALYSIS / ACCOUNT / REFERENCE)
- **v23** (8c8fcda): fixed extra `</div>` from v22 that pushed views outside `<main>` — Settings layout now correctly nested
- **v24** (ebcc261): boxed filter chips (14px bold), proper click boxes with borders, Sources spinner replacing chips, Watch+Sources share a row
- **v25** (b18f3b1): hide native number input spinner arrows on Sources (redundant with +/- buttons)
- **v26** (77c48da): major v26 redesign — Parallax-inspired story cards with topic pills (color-coded by region), date/sources pills in mono, serif headline (Georgia 19px), editorial confidence badges (VERIFIED/CORROBORATED/MULTI-SOURCE/SINGLE SOURCE/UNVERIFIED), ECON/PREDICTION/PSYOP flag chips, newest-first sort, click-to-expand (Situation/Connections/Cascading effects/Narrative shift sections), Source Registry view with 6 tier-badged groups (hardcoded)
- **v27** (50d55ee): wired frontend `renderStoryCardV2` to existing backend fields — `category` drives topic pill (conflict-war/politics/economics/human-rights/environment/technology/disinformation with dedicated color classes), `location` renders inline after topic, `confidence` from AI shown as hint under badge. Source Registry now fetches `/sources.json` with hardcoded fallback. Added `ground_truth` and `who_benefits.civilian_impact` to expanded card
- **v28** (68192e6): added `/sources.json` Flask route in main.py — reads RSS_FEEDS, groups by `lean` field into tiers via `tier_map` dict. First version covered 6 lean values (67 feeds fell into "Other sources")
- **v29** (ce3aed8): expanded `tier_map` to cover all 31 real lean values in RSS_FEEDS → 8 proper groups (Wires & mainstream 25, Primary documents 16, Policy & think tanks 3, Regional specialist 11, Investigative & OSINT 10, Conflict analysis 9, Humanitarian & human rights 5, State media monitored 4). Zero "Other" stragglers. Source Registry view confirmed live-wired to backend (83 cards render, 44 T1 / 35 T2 / 4 T3)
- **v30** (60b8259): CONTEXT.md — added v20-v29 entries, bumped heading to end-of-v29 session
- **v31** (3018074): parallax.html — `renderStoryCardV2` handles brief top_stories schema's `source` (singular, comma-separated string). Before: "0 SOURCES / UNVERIFIED" on real brief cards. After: "8 SOURCES / VERIFIED" on Iran Hormuz
- **v32** (ba3b267): JSON repair in `generate_story()` at main.py:2674 — trim pre/post-blob text, kill trailing commas before `json.loads`. Additive only. Turned out to be irrelevant: stories=0 bug was NOT JSON-parse.
- **v33** (ad366c9): `call_claude` default max_tokens 900→4000 to prevent truncation. Didn't help — bug was upstream, call never returned.
- **v34** (a98b814): added `_DEBUG_STORY_GEN` in-memory log + `/debug-story-gen` endpoint. **Gave us the definitive answer**: all 20 clusters failed at `claude_empty` stage — not JSON, not tokens, the Claude API call itself was returning empty. Root cause: **credit balance exhausted** ($21.60 grant burned, -$0.76 unpaid balance). Fixed when user bought more credits.
- **v35** (8bf23da): route JSON files through `/data` volume with `DATA_DIR` env+fallback logic. All 5 file paths (BRIEF_FILE, DATA_FILE, VELOCITY_FILE, NARRATIVE_FILE, STORY_HISTORY_FILE) use `os.path.join(DATA_DIR, ...)`. Auto-creates dir. **Persistent storage finally live** — no more losing state on every push.
- **v36** (46db150): **major UI rebuild for intel-community demo**: region-grouped layout, compact-first cards (click to expand), threat level meter per region (horizontal bar: routine/elevated/active/urgent), delta indicators (↑ +N / ↓ -N / ↔ flat), global overview strip (Stories / Regions / Verified / Top Watch). Uses existing backend fields — zero Python changes, +8,239 chars HTML

---

## Brand identity (LOCKED)

**This was designed carefully with Tyler over many turns. Do not change without explicit approval.**

- **Name:** Vantage
- **Tagline:** One event. Every perspective.
- **Colors:**
  - Dark mode bg: `#0b0d10` (soft black)
  - Light mode bg: `#e8e2d0` (cream)
  - Steel accent: `#7a8a97`
  - Dark mode text: `#f5efe0` (brighter cream — this is the color to use for text, NOT the lighter `#ebe4d3` which was too muted)
  - Light mode text: `#0b0d10`
- **Emblem:** split circle, 15° clockwise tilt, offset halves creating parallax effect.
  - Steel half (`#7a8a97`) is on BOTTOM-RIGHT in both modes — constant.
  - Top-LEFT half flips: cream (`#f5efe0`) in dark mode, ink (`#0b0d10`) in light mode.
- **Watch level** (replaces "threat level"): 4 tiers, muted stoplight colors:
  - 🟢 Routine (`#4ea86a`)
  - 🟡 Elevated (`#c9a63b`)
  - 🟠 Active (`#c97a3b`)
  - 🔴 Urgent (`#c94a3b`)
  - JSON `threat_level` values map: low→routine, moderate/elevated→elevated, high→active, severe/urgent/critical→urgent
  - No numeric score. Do not add one.
- **Typography:** Inter/system sans-serif for UI. Georgia serif for headlines/editorial moments only.
- **Vibe:** "A newspaper room run by people who trained at Langley" — FT gravitas + Palantir precision + Linear warmth.

---

## Product positioning (LOCKED)

- **Primary audience:** ex-intel and active intel-community professionals. Every design decision prioritizes them.
- **Secondary audience:** curious average Joe, as long as they're willing to think. Lose the TikTok-news person permanently — right person to lose.
- **Pricing:** ~$30/mo target tier eventually. Tiered free/paid plans are Phase 3+, not MVP.
- **MVP rule:** Must run 30 days without incident before Phase 2 features ship (reduced from 100 during testing phase).

### Perspectives framework (every brief applies this)

1. Washington/Brussels
2. Moscow/Beijing
3. Global South
4. Regional actors
5. Financial capital

Each brief asks: what does this look like from each vantage?

### Reasoning lenses (used selectively per story)

Realist, structural/Marxist, civilizational, game-theoretic, psychoanalytic, primary-source literalist.

---

## Sections in UI

- **Daily brief** — fetches `/brief.json`, renders watch banner, headline, intelligence overview, top stories (tap to expand), overnight signals, contested numbers, analyst note, sources. LIVE.
- **All stories** — fetches `/stories.json`, renders story list with source count. LIVE.
- **Predictions** — Phase 2 placeholder. Will track forecasters with probability scores.
- **Psyops** — Phase 2 placeholder. Silence detection + narrative-divergence tracking.
- **Conspiracy** — DROPPED for MVP (legal/reputational risk).

---

## Phase roadmap (LOCKED)

### Phase 1 (MVP — current)
Stable daily brief, stories feed, basic UI. Must run 100 days stable before any Phase 2 work starts. No new features.

### Phase 2 (post-100-days)
- Predictor feeds (no scoring yet — just tagged by author)
- Silence detection (flag when Western wires skip stories non-Western sources cover)
- Foreign-language translation (Russian, Chinese, Arabic, Farsi, Spanish, Turkish — highest-leverage differentiator)
- Source expansion to ~50-60 total (staged list — see below)


### Phase 2 deferred (explicit list — from v36 session)

User asks from 2026-04-19 session that we deferred to Phase 2 because they genuinely require infrastructure we don't have yet:

1. **User accounts + cross-device saved feeds** — requires full auth system (signup/login/password-reset/session management/per-user DB). 1-2 weeks of engineering. Defer until we have 10+ beta testers who actually need cross-device persistence.
2. **Push / email notifications** — requires accounts (see #1) + service integration (SendGrid / OneSignal / Firebase). Cost ~$15-50/mo baseline. Defer with accounts.
3. **Real satellite feed integration** — Sentinel Hub Enterprise = $250/mo minimum, Planet Labs = thousands. Skip until there's paying enterprise demand. MVP can use free NASA GIBS (MODIS daily imagery) as a layer on the map, and link out to Sentinel Hub EO Browser when a story has coordinates.

These are GOOD ideas, not wrong ideas. They're just expensive in engineering time or operational cost and would delay getting the MVP in front of testers.

### Phase 2 shipped in v37 (scoped-down versions of those user asks)

- **Location filter down to city** (uses existing `s.location` field — pure frontend)
- **Interactive map view with draw-a-rectangle filter** (Leaflet + OpenStreetMap, free, no auth)
- **Optional NASA GIBS satellite layer toggle** (free, no API key)
- **"Create a Card" custom feeds saved to localStorage** (per-browser, no accounts, ~$0.05 Claude call per card)

When we add real accounts later, migrate localStorage feeds to server-side per-user storage.

### Phase 3+
Track-record scoring, narrative clustering, framing divergence, entity dossiers, watchlists, tiered free/paid plans.

### Explicitly rejected / deferred
- Video or war-footage analysis (cost + verification + legal)
- Broad podcast transcription (Phase 3+, selective only)
- Multi-AI disagreement panel
- Broad social media scraping
- Auto-reload billing
- Source expansion above ~60 (hurts Claude's brief quality at current context limits)

### Phase 2 source expansion (staged, do not add yet)

Regional (10): Haaretz, Times of Israel, The Hindu, The Wire India, Der Spiegel, Le Monde, Nikkei Asia, Folha de São Paulo, Daily Sabah, Hurriyet.
Defense/military (6): War on the Rocks, Breaking Defense, The War Zone, Defense One, RUSI Commentary, Institute for the Study of War.
Think tanks (6): CSIS, Carnegie Endowment, Chatham House, Quincy Institute, Valdai Club, Observer Research Foundation.
OSINT/conflict (4): ACLED, Oryx blog, Liveuamap, Critical Threats Project.
Geoeconomic (4): FT Alphaville, Adam Tooze Chartbook, Patrick Boyle, Zoltan Pozsar.
Primary docs (3): SEC EDGAR, Federal Register, DOD press briefings.

---

## Technical reference

### Key line numbers in main.py (as of v15)

- **Line 60:** `SCRAPE_INTERVAL_MINUTES = 720` (v19)
- **Line 2823:** `"max_tokens": 16000` — brief API call (v11)
- **Line 3175:** `return send_file("parallax.html")` — `/` route (v15)
- **Lines 2853-2894:** JSON repair block in `generate_daily_brief()` (v8)
- **Lines 3219+:** `/debug-brief` route (v10)

### /debug-brief usage

`GET /debug-brief?file=raw|repaired&pos=<char>&ctx=<radius>`

Returns `{file, size_chars, all_files, pos, context, char_at_pos, ord_at_pos}`.

**Files wipe on Railway redeploy** — filesystem is ephemeral.

### Railway GraphQL log pattern (from browser console, credentials:include required)

```js
fetch('https://backboard.railway.com/graphql/v2', {
  method:'POST',
  credentials:'include',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify({
    query:'query GetLogs($deploymentId:String!,$filter:String,$limit:Int){deploymentLogs(deploymentId:$deploymentId,filter:$filter,limit:$limit){message timestamp severity}}',
    variables:{deploymentId:"<DEPLOYMENT_ID>", filter:"Brief", limit:30}
  })
})
```

Get current deployment ID from Railway tab: `document.querySelectorAll('a[href*="id="]')[0].href.match(/id=([a-f0-9-]+)/)`

### Brief generation timing

~3-4 min from `/trigger-brief` (GET) to `/brief.json` returning 200. Occasionally up to 5 min.

### Expected brief JSON structure (13 fields)

`date`, `generated_at`, `threat_level`, `threat_level_reason`, `headline_brief`, `intelligence_overview`, `top_stories` (array of 5-6), `overnight_signals` (5-8), `contested_numbers_today` (1-3), `analyst_note`, `sources_consulted` (array, 30-50 typical), `generated_at_iso`, `generated_by`.

### CM6 edit pattern on GitHub web editor

Works reliably on all GitHub edit pages. Use it instead of `type` action which triggers auto-indent chaos:

```js
const view = document.querySelector('.cm-content').cmTile.view;
// Insert:
view.dispatch({ changes: { from: pos, insert: code } });
// Line-targeted replace:
const line = view.state.doc.line(N);
view.dispatch({ changes: { from: line.from, to: line.to, insert: newText } });
// Always verify after:
view.state.doc.line(N).text
```

### Verification rule

After every commit: fetch raw file from `raw.githubusercontent.com/tylerjosephjohnson-alt/parallax-intel/main/<file>` and confirm the change landed. Don't trust the editor — trust main.

---

## Claude working relationship with Tyler

- **Address him as "sir".** Polite register (please, thank you).
- **During tool work:** terse factual status updates. No explanatory preambles.
- **During planning/conversation:** personable, questions, opinions, humor, push back when disagreeing — but don't announce the pushback, just do it honestly.
- **3-try rule:** If iterating on the same element 3 times fails, stop and flag for Tyler instead of trying a 4th.
- **Path B collaboration model:** Tyler owns vision, content, product decisions, go-to-market. Claude handles code, Railway, deploys, auth, reliability. Tyler learns selectively but isn't trying to become a backend engineer.

### Tyler's shorthand (recognize these)

- "inop" = broken/inoperative
- "cridits" = credits
- "done" = I completed the action you asked for
- Casual typing, skip demanding perfect grammar back — he wants substance not correction

### Tyler's autonomy permissions (as of end of v15 session)

These were granted when Tyler stepped away for the Path C rebuild. Renegotiate next time he hands off.

- Rename/commit/create files: ✅
- Change single lines in main.py for file reference updates: ✅
- Trigger briefs to verify, spending under $1 total: ✅
- Update CONTEXT.md: ✅

Forbidden without asking:
- Deletions of anything
- Backend logic changes (scraper, brief generator, Claude API call structure)
- Scrape interval changes
- Env vars or Railway settings
- DNS / domain changes
- Spending over $1 in a single autonomous block

---

## What next session should probably do

1. Confirm brief finishes generating and renders cleanly in Daily brief view
2. If scraper has run, check All Stories view renders too
3. Screenshot both views for Tyler to see the final product
4. Ask about next priorities: domain purchase, Phase 2 planning, or 100-day stability watch

## Success criteria for MVP complete

- `/` returns 200 with Vantage UI ✅
- Daily brief view renders real brief data cleanly
- All stories view renders real stories
- Theme toggle works both directions ✅
- Nav swaps views without console errors ✅
- No stale legacy content visible to users ✅
- Runs 30 days without crashing — the finish line for Phase 1 (reduced from 100 during testing phase)

Current state: 4 of 7 boxes checked. Two more depend on scraper/brief finishing; the 100-day test is where we are now.
