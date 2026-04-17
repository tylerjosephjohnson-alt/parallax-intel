# Parallax Project Status

## Live URL
https://web-production-532874.up.railway.app
Login password: parallax2026

## Accounts & Services
- **GitHub repo:** github.com/tylerjosephjohnson-alt/parallax-intel
- **Railway project:** grateful-liberation, service "web" (us-west2)
  - Railway project ID: dfd3cd10-374d-4db1-9ba6-9672e0e4260a
  - Service ID: 3442072e-951d-4566-b7da-6effd4f831d1
- **Anthropic:** Master's Individual Org, API billing active
  - $20 credit purchased 2026-04-17
  - Auto-reload: OFF (should enable to avoid interruptions)
- **Replit:** replit.com/@tylerjohnson190/Python-Power (BACKUP ONLY — not used live)

## Current Deployment State (as of 2026-04-17)
- Latest working deployment: v7 (main.py 167KB on GitHub)
- Scraper works: 391+ articles, 20 stories per cycle
- Brief generation: **blocked on JSON parse hiccup** — Claude returns valid brief text with minor JSON syntax errors (~char 30000, line 82-98 range)

## Outstanding Bug
`Brief error: Expecting ',' delimiter: line X column Y (char Z)`
Claude generates a complete 30k-character brief in ~3 minutes, but the JSON has minor formatting errors that break `json.loads()`. Happens consistently (tested twice, line 82 then line 98).

**Fix staged but not uploaded: v8 (main-FIXED-v8.py)**
- Adds robust JSON parsing: strict parse → repair (strip trailing commas, backticks) → retry → save raw output for debug if still failing

## Version History
| Version | Key Fixes |
|---|---|
| v1-v3 | HTML fixes (escaped backticks, orphaned setView, sidebar nav) |
| v4 | last_run init, FRED_SERIES={}, moved 4 functions above __main__, sid fix |
| v5 | Fixed sources[:8] set-slice crash, fromisoformat(None) guard, removed deprecated anthropic-beta headers (2 places), added error body capture |
| v6 | Fixed set-slice in prompt f-string at line 2555 (tiers/leans) |
| v7 | Brief timeout 120s→300s, populated FRED_SERIES with 12 real indicators |
| v8 (STAGED) | Robust JSON parsing for brief output |

## Roadmap (agreed with user)
### Phase 1 — Free intelligence upgrades
1. ✅ Real FRED economic indicators (v7)
2. ⏳ Curated "predictor" feeds (30 Substacks with track records)
3. ⏳ Historical thinker lenses (Sun Tzu, Kennan, Mearsheimer, etc.)
4. ⏳ Source silence detection (who's NOT covering a story)
5. ⏳ Devil's advocate toggle
6. ⏳ Retrospective accuracy scoring
7. ⏳ Vector embeddings for past-article similarity (Cascade++)

### Phase 2 — UI/workflow
8. Entity pages (per-actor dossiers)
9. Watchlists + alerts
10. Provenance-as-UI (clickable source citations)
11. Time-stamped prediction cards
12. Devil's advocate UI button

### Phase 3 — User's design changes (TBD)

### Explicitly deferred
- Multi-AI disagreement panel (user said "not sure yet")
- Broad social media scraping (paid)
- Video analysis (too expensive)

## Known RSS feed failures (non-blocking)
Graceful fallback, not a bug. Some sources 403/404:
Reuters, AP, AFP, UN Press, ICC, IAEA, OHCHR, OFAC, SIPRI, OpenSanctions, IMF, World Bank, some Bloomberg articles

## Working RSS sources (confirmed)
BBC, Guardian, Bloomberg, FT, Al Jazeera, SCMP, TASS, Dawn, IranWire, Foreign Policy, ICG, Bellingcat, Intercept, ProPublica, ICIJ, Stimson, Sudan War Monitor, BIRN, ReliefWeb, Middle East Eye, Seymour Hersh, Emptywheel, Ken Klippenstein

## User context
- User = Tyler Johnson, beginner-level coding
- Uses casual shorthand ("inop" = broken, "riplit" = Replit)
- Claude for Chrome extension active — Claude can navigate browser
- Cannot do OS file picker interactions (native dialogs not accessible)
- User uploads files manually after download

## Next Session Should
1. Read this PROJECT.md first (source of truth)
2. Regenerate `main-FIXED-v8.py` with robust JSON parsing (spec above)
3. Walk user through GitHub upload
4. Verify brief generates successfully (wait full 4 min)
5. Update this PROJECT.md with results

## Cost notes
- Each brief: ~$0.10 (web search + 8k tokens out)
- Each scraper cycle: ~$0.40 (20 story cards @ $0.02)
- Scrape interval: every 30 min = $19/day 24/7 if running constantly
- $20 should last ~24 hours at current rate. Consider increasing scrape interval or using Haiku for story cards.
