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

## Current state (end of v15 session, 2026-04-17)

### What works
- Backend brief generation — returns valid 44K-char JSON with all 13 fields
- New clean Vantage UI live at `/` — loads in both dark and light modes, nav swaps views, theme toggle works, zero JS errors on current page
- `/debug-brief` endpoint for inspecting brief generation failures
- Scraper running at 420-min interval (~$1/day cost)
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
- **MVP rule:** Must run 100 days without incident before Phase 2 features ship.

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

- **Line 60:** `SCRAPE_INTERVAL_MINUTES = 420` (v12)
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
- Runs 100 days without crashing — the finish line for Phase 1

Current state: 4 of 7 boxes checked. Two more depend on scraper/brief finishing; the 100-day test is where we are now.
