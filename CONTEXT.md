# Parallax — Full Context for Next Claude Session

**IMPORTANT:** Read this entire file before doing anything. It contains everything you need to pick up the project cleanly. Follow its instructions literally.

---

## Quick reference

- **Live URL:** https://web-production-532874.up.railway.app
- **App login password:** `parallax2026`
- **GitHub repo:** github.com/tylerjosephjohnson-alt/parallax-intel
- **Railway project ID:** dfd3cd10-374d-4db1-9ba6-9672e0e4260a
- **Railway service ID:** 3442072e-951d-4566-b7da-6effd4f831d1
- **Anthropic account:** "Master's Individual Org", $20 credit added 2026-04-17, auto-reload OFF

---

## Current state (2026-04-17)

- **Deployed version:** v7 (~167KB) — scraper works (391 articles, 20 stories)
- **Outstanding bug:** brief generation fails because Claude's ~30k-char brief JSON has small syntax errors (trailing commas, smart quotes). Fix is v8 below.
- **Anthropic credits:** Working. Key valid. Billing fine. 401 and "credit too low" errors from earlier were red herrings.

---

## THE CURRENT TASK — v8 patch

Apply TWO changes to `main.py` on GitHub via the web editor. Both are small paste-replace operations. Commit together.

### Change 1: Robust JSON parsing in brief generator

**Find this 5-line block** (inside `generate_daily_brief()`, around line 2854):

```python
        clean = text.replace("```json","").replace("```","").strip()
        j_start = clean.find("{")
        j_end   = clean.rfind("}") + 1
        brief   = json.loads(clean[j_start:j_end])
```

**Replace with:**

```python
        clean = text.replace("```json","").replace("```","").strip()
        j_start = clean.find("{")
        j_end   = clean.rfind("}") + 1
        json_text = clean[j_start:j_end]

        # v8 robust JSON parse: strict -> repair pass -> debug fallback
        try:
            brief = json.loads(json_text)
        except json.JSONDecodeError as parse_err:
            print(f"  Brief: strict parse failed at {parse_err}, attempting repair")
            import re as _re
            repaired = json_text
            # Normalise smart quotes and fancy dashes Claude emits
            _smart = {
                "\u201c": '"', "\u201d": '"',
                "\u2018": "'", "\u2019": "'",
                "\u2013": "-", "\u2014": "-",
                "\u2026": "...", "\u00a0": " ",
            }
            for _bad, _good in _smart.items():
                repaired = repaired.replace(_bad, _good)
            # Strip stray backtick fences left mid-document
            repaired = repaired.replace("```", "")
            # Remove trailing commas before } or ]
            repaired = _re.sub(r",(\s*[}\]])", r"\1", repaired)
            # Remove stray // line comments
            repaired = _re.sub(r"^\s*//[^\n]*$", "", repaired, flags=_re.MULTILINE)
            try:
                brief = json.loads(repaired)
                print(f"  Brief: repair successful")
            except json.JSONDecodeError as repair_err:
                print(f"  Brief: repair failed too ({repair_err})")
                try:
                    ts = utc_now().strftime("%Y%m%d-%H%M%S")
                    with open(f"brief-raw-{ts}.txt", "w", encoding="utf-8") as f:
                        f.write(text)
                    with open(f"brief-repaired-{ts}.txt", "w", encoding="utf-8") as f:
                        f.write(repaired)
                    print(f"  Brief: wrote debug files brief-raw-{ts}.txt")
                except Exception:
                    pass
                raise
```

### Change 2: Change scrape interval to hourly

**Find line 60:**

```python
SCRAPE_INTERVAL_MINUTES = 30
```

**Replace with:**

```python
SCRAPE_INTERVAL_MINUTES = 60
```

Reason: Cuts cost from ~$15/day to ~$7.50/day. User approved.

### Commit message for both:

```
v8: robust JSON parsing + hourly scrape interval
```

### After commit:

1. Wait ~60s for Railway redeploy
2. Verify via `raw.githubusercontent.com/.../main.py` that `v8 robust JSON parse` is present
3. POST to `/trigger-brief` on the live URL
4. Wait 4 minutes (briefs take 2-3 min)
5. GET `/brief.json` — should be 200 with valid brief
6. Report headline and threat_level to Tyler

If brief still fails, fetch Railway logs via GraphQL (pattern below) to read the error body. Do NOT invent new fixes without showing Tyler the actual error first.

---

## APPROACHES THAT DO NOT WORK — DO NOT USE

Previous Claude wasted multiple turns on these. **Do not repeat them:**

1. **Do NOT write a patcher script** — this forces Tyler to run Terminal commands. He can't.
2. **Do NOT try to write the full 170KB file in one `create_file` call** — it gets truncated.
3. **Do NOT invent 3 new approaches per turn** — pick one and finish it.
4. **Do NOT ask Tyler to run any CLI tool** — browser-only.
5. **Do NOT download v7 to sandbox and re-present** when a GitHub web editor paste works.

## THE ONLY WORKING APPROACH

For main.py changes under ~100 lines: fetch current v7 from `raw.githubusercontent.com/.../main.py`, compute the patched string in JavaScript, then either:
- (a) tell Tyler to paste the replacement block in GitHub's web editor, OR
- (b) offer the patched file as a browser download with a **distinct non-`main.py` filename** and have Tyler rename+upload.

For main.py changes over ~100 lines: use `create_file` in chunks via the sandbox, verify `python3 -m py_compile`, then `present_files`.

---

## ANALYTICAL POSTURE — THE HEART OF THE PRODUCT

Parallax exists to produce intelligence analysis from **all perspectives**, not Western-aligned news summary. Every prompt change must preserve this. Bake these rules into every Claude call in the codebase.

### The 5 required perspectives
For every story/brief, explicitly model how it reads in at least 5 rooms:
1. **Washington/Brussels** (US-Atlantic establishment)
2. **Moscow/Beijing** (revisionist power view)
3. **Global South** (Africa/Asia non-aligned — not just governments, also Modi/Lula/AMLO/Ramaphosa types)
4. **Regional actors directly affected** (what does Tehran/Istanbul/Khartoum/Kyiv actually see)
5. **Financial capital** (Wall Street, City of London, Gulf sovereign wealth — who profits, who's shorting)

### Reasoning lenses to apply
- **Realist** (Mearsheimer, Morgenthau): whose power increased/decreased
- **Structural/Marxist**: whose capital deployed, whose class interests served
- **Civilizational** (Huntington, Dugin): each actor's self-narrative
- **Game-theoretic** (Schelling): what signal sent, what credible threat
- **Psychoanalytic** (states): what insecurity drives this, what face saved
- **Primary-source literalist**: what OFAC filings, IAEA reports, ACLED data, court transcripts, leaked cables actually say (not what headlines say about them)

### Claims hygiene
- Never state as fact what only one side claims. Attribute: "According to Reuters" / "Russian MoD stated."
- When casualty figures disagree, list ALL figures with structural reasons each side has to over/under-count.
- Silence is a signal: note who did NOT comment, did NOT publish usual coverage, did NOT sanction.
- Four labels, use explicitly: documented fact / one-sourced claim / reasoned inference / speculation.

### Historical pattern matching (NOT just Western canon)
- Ancient: Thucydides, Sun Tzu, Kautilya's Arthashastra
- Early modern: Machiavelli, Clausewitz, Mahan
- 20th c.: Kennan, Kissinger, Brzezinski — also Gramsci, Fanon, Mao, Khomeini
- Track-record analysts: Taleb (financial fragility), Mearsheimer (NATO expansion), Pozsar (dollar plumbing), Michael Burry (2008)

### Specific beneficiaries — always name
"Arms industry" is not sufficient. Name Raytheon, Lockheed, Elbit, Rheinmetall, Norinco. "Tech companies" is not sufficient — Palantir, Anduril, Helsing. Trace money to specific tickers or named private actors.

### What mainstream missed
Every brief needs a "buried lede" paragraph: what's in regional specialist sources, primary documents, or local-language media that didn't make Western front pages.

### Epistemic humility
- Confidence must match evidence. One source = down-rank confidence.
- Predictions must be falsifiable and dated: "If X hasn't happened by [date], this was wrong."
- Two rigorous analysts disagree? Show both. Don't paper over.

### Prompt engineering pattern for new Claude calls
Wrap every prompt with:
- "Perspectives required" list (the 5 rooms)
- "Contested claims must stay contested"
- "Name specific actors"
- "Buried lede / what mainstream missed"

### Things NOT to put in prompts
- "Summarize the news" → produces mainstream slop
- "Balanced coverage" → produces false equivalence
- Default US/NATO framing as neutral baseline
- Treating Reuters/AP as inherently more trustworthy than Al Jazeera/SCMP/TASS. Weight by primary-source access, track record on the specific beat, structural incentive to distort.

### When building roadmap features
- **Thinker lenses** must include non-Western thinkers (Ibn Khaldun, Mao, Gandhi, Khomeini, Kautilya — not just Western canon)
- **Source silence detection** must flag when Western wires skip stories non-Western sources cover, AND when state media avoids something usually covered
- **Devil's advocate** must be rigorous adversarial, not "on the other hand"
- **Predictor feeds** must span civilizational perspectives: Pozsar (West finance), Pepe Escobar (Global South), Yan Xuetong (Chinese strategy), Sreeram Chaulia (India), regional experts

### The heart of it
Parallax exists because mainstream analysis is structurally captured by whoever pays for it. The platform's value is showing the reader the SAME event through 5+ genuine lenses, naming the material interests driving each view, and preserving the uncertainty that mainstream erases. Every feature must serve this.

---

## WORKING WITH TYLER — COLLABORATION GUIDE

### About Tyler
- Beginner-level at coding. Understands concepts when explained; doesn't read code.
- Casual shorthand: "inop" = broken, "riplit" = Replit, "cridits" = credits.
- Terse confirmations ("done", "do it") mean action was taken.
- **Browser-only workflow** — no Terminal, no native file picker.
- Claude for Chrome extension active; can navigate tabs and read DOM.

### How to respond
- **Pick ONE approach per problem. Finish it before considering alternatives.**
- Don't offer "3 options" when an obviously best one exists — just do it.
- Explain decisions, not code details, unless asked.
- Minimal markdown. Bold only for critical warnings. No emojis unless celebrating.
- Short messages unless depth was requested.
- When proposing user action, give exact step-by-step with no assumed knowledge.

### Don't
- Don't write patcher scripts as workarounds for your own limits.
- Don't download files to Tyler's Mac unless the change is large.
- Don't ask Tyler to run Terminal commands. Ever.
- Don't context-switch mid-debug.
- Don't touch Railway settings, Anthropic key, or env vars without asking.
- Don't delete GitHub commits.
- Don't invent three approaches per turn.

### Session hygiene
- Start every session by fetching this CONTEXT.md from GitHub raw.
- End important sessions by committing an update to this file's "current state" section.
- When staging files to sandbox, use `parallax-fixed-v<N>.py`. Always bump N.
- Before any patch, verify against current GitHub version.

### Budget discipline
- Anthropic credits: $20 purchased 2026-04-17. Burn rate ~$15/day at 30-min scrape (will drop to ~$7.50/day at hourly scrape once v8 ships).
- Flag cost impact before enabling expensive features.
- Haiku is 5× cheaper than Sonnet — good for story cards. Sonnet only for briefs and devil's-advocate.
- Mention: "This change will cost ~$X/day more."

### "Working" verification checklist
Before saying "done" to Tyler:
- [ ] Fetched main.py from GitHub raw, confirmed change landed
- [ ] Verified via HTTP that relevant endpoints return 200 not 500
- [ ] Checked Railway logs for errors in last 2 min
- [ ] Tested specific feature end-to-end (trigger → wait → fetch → inspect)
- [ ] Only then say "done" with a summary of what you verified

### When stuck
- If 2 approaches fail, stop and ask Tyler what he wants.
- If Tyler is confused, don't pile on more options — ask one focused question.
- If tempted to say "there are a few things we could try," pick one instead.

---

## DECISIONS LOG

### Architecture
- **[ACCEPTED] Railway for hosting** over Replit. Replit had auth/thread issues.
- **[ACCEPTED] GitHub as single source of truth.** Railway auto-deploys from main. Never edit files on Railway or Replit directly.
- **[ACCEPTED] Single-file main.py (~170KB).** Not ideal. Don't refactor without explicit user request.
- **[ACCEPTED] stories.json as flat file, not database.** Good enough for MVP.
- **[ACCEPTED] claude-sonnet-4-6** for story cards and briefs. Consider Haiku for story cards later.

### Features
- **[REJECTED] Multi-AI disagreement panel** (Claude + GPT + Gemini). User said "not sure yet." Don't add without approval.
- **[REJECTED] Broad social media scraping** (X/Twitter, TikTok, Instagram). Cost and legal exposure too high. Use existing Telegram/Bluesky/Reddit.
- **[REJECTED] Video analysis frame-by-frame.** Prohibitive cost. Alternative: LINK to livestreams, don't analyze.
- **[REJECTED] Auto-reload billing.** User controls spend manually for now.
- **[ACCEPTED] FRED economic indicators overlay.** 12 series in v7.
- **[ACCEPTED] Web search tool in brief generation.** Essential for overnight context.
- **[ACCEPTED] 300s timeout on brief API call.** Briefs take 2-3 min.
- **[ACCEPTED] Robust JSON parsing with repair pass (v8).**
- **[ACCEPTED] Hourly scrape interval** (was 30 min). Cost reduction.

### Scope
- **[DEFERRED] Predictor track-record scoring.** Phase 1 feature. Build after MVP.
- **[DEFERRED] Vector embeddings for past-article similarity (Cascade++).** Phase 1.
- **[DEFERRED] Entity dossier pages.** Phase 2.
- **[DEFERRED] User watchlists and alerts.** Phase 2.
- **[DEFERRED] Translation-gap detector.** Phase 2.
- **[REJECTED for MVP] Real user accounts / authentication.** One shared password is fine for MVP.

### Things that look like bugs but aren't
- **RSS 403/404s** (Reuters, AP, AFP, UN, ICC, IAEA, OHCHR, OFAC, SIPRI, IMF, World Bank). Graceful fallback is correct. Don't "fix" one by one.
- **/brief.json 404** — normal until first successful brief. 200 forever after.
- **stories.json "generated_at": "2026-04-17T00:00:00Z"** — placeholder, replaced after first scrape.

---

## MVP DEFINITION — ship before Phase 2

Don't add new features until ALL of these work:
1. Scraper runs every 60 min without crashing
2. `/stories.json` returns 15+ stories with full structured fields
3. `/brief.json` returns a valid brief JSON
4. `/status` returns 200 with real counts
5. UI renders both without JS errors
6. Sources are clickable on every claim

Only after all 6 are green: Phase 2 (entity pages, watchlists, predictor feeds, vector search, thinker lenses, devil's advocate).

---

## ROADMAP (after MVP)

### Phase 1 — Free intelligence upgrades
1. ✅ Real FRED economic indicators (v7)
2. ⏳ Curated "predictor" feeds (30 Substacks with track records)
3. ⏳ Historical thinker lenses (Sun Tzu, Kennan, Mearsheimer, Ibn Khaldun, Mao, Gandhi, Kautilya, etc.)
4. ⏳ Source silence detection (who's NOT covering a story)
5. ⏳ Devil's advocate toggle
6. ⏳ Retrospective accuracy scoring
7. ⏳ Vector embeddings for past-article similarity (Cascade++)

### Phase 2 — UI/workflow
8. Entity pages (per-actor dossiers)
9. Watchlists + alerts
10. Provenance-as-UI (clickable source citations on every claim)
11. Time-stamped prediction cards
12. Devil's advocate UI button

### Phase 3 — User's design changes (TBD, discussing later)

### Explicitly rejected from roadmap
- Multi-AI disagreement panel (user said "not sure yet")
- Broad paid social media scraping
- Video analysis

---

## RSS SOURCE STATUS

### Working (confirmed)
BBC, Guardian, Bloomberg, FT, Al Jazeera, SCMP, TASS, Dawn, IranWire, Foreign Policy, ICG, Bellingcat, Intercept, ProPublica, ICIJ, Stimson Center, Sudan War Monitor, BIRN, ReliefWeb, Middle East Eye, Seymour Hersh, Emptywheel, Ken Klippenstein

### Failing (graceful fallback — not bugs)
Reuters, AP, AFP, UN Press, ICC, IAEA, OHCHR, OFAC, SIPRI, OpenSanctions, IMF, World Bank, some Bloomberg article URLs

---

## VERSION HISTORY

| Version | Fixes |
|---|---|
| v1-v3 | HTML fixes (escaped backticks, orphaned setView, sidebar nav) |
| v4 | last_run init, FRED_SERIES={}, moved 4 functions above __main__, sid fix |
| v5 | sources[:8] set-slice fix, fromisoformat(None) guard, removed deprecated anthropic-beta headers, added error body capture |
| v6 | set-slice fix in prompt f-string at line 2555 (tiers/leans) |
| v7 | brief timeout 120s→300s, populated FRED_SERIES with 12 real indicators |
| v8 (CURRENT TASK) | Robust JSON parsing for brief + hourly scrape interval |

---

## RAILWAY LOGS — HOW TO FETCH

Use GraphQL via Tyler's authenticated session:

```javascript
fetch('https://backboard.railway.com/graphql/v2', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify({
    query: `query GetLogs($deploymentId: String!, $filter: String, $limit: Int) {
      deploymentLogs(deploymentId: $deploymentId, filter: $filter, limit: $limit) {
        message timestamp severity
      }
    }`,
    variables: {
      deploymentId: "<current-deployment-id>",
      filter: "Brief",
      limit: 50
    }
  })
}).then(r => r.json())
```

Get `<current-deployment-id>` by navigating to Railway service page and reading `a[href*="id="]` — the first match is newest.

---

## SUCCESS LOOKS LIKE

When v8 is deployed and a brief generates successfully:
- `/brief.json` returns 200
- Response has fields: `headline_brief`, `threat_level`, `intelligence_overview` (4 paragraphs), `top_stories` (5-6), `overnight_signals`, `contested_numbers_today`, `analyst_note`, `sources_consulted`
- Railway logs show `Brief generated: [headline]` and `Threat level: [value]` and `Top stories: [count]`
- Tyler sees it render in the UI under the "Daily Brief" nav section

That's the finish line for today.
