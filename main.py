"""
Parallax — Replit auto-runner
Paste this as main.py in a new Replit Python project.
Add ANTHROPIC_API_KEY in Replit Secrets (padlock icon).
The Flask server serves the app + stories.json.
The background thread runs the scraper every 30 minutes.

Requirements (install in Replit shell):
  pip install newspaper4k trafilatura
  pip install spacy && python -m spacy download en_core_web_sm  # optional but recommended
"""

import json, os, hashlib, time, re, threading
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

# ── Full article extraction — graceful fallback if not installed ──
try:
    import newspaper
    NEWSPAPER4K = True
    print("newspaper4k available — full article extraction enabled")
except ImportError:
    NEWSPAPER4K = False
    print("newspaper4k not installed — using RSS descriptions only")
    print("  Install with: pip install newspaper4k")

try:
    import trafilatura
    TRAFILATURA = True
    print("trafilatura available — used as fallback extractor")
except ImportError:
    TRAFILATURA = False

# ── Named entity extraction — optional accuracy boost ──
try:
    import spacy
    try:
        NLP = spacy.load("en_core_web_sm")
        SPACY = True
        print("spaCy NER available — entity extraction enabled")
    except OSError:
        SPACY = False
        print("spaCy model not found — run: python -m spacy download en_core_web_sm")
except ImportError:
    SPACY = False

try:
    from flask import Flask, send_file, jsonify, send_from_directory, request
    FLASK = True
except ImportError:
    FLASK = False

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SCRAPE_INTERVAL_MINUTES = 720
BRIEF_HOUR_UTC       = 5   # Generate daily brief at 05:00 UTC
BRIEF_FILE           = "brief.json"
MAX_STORIES = 20
HOURS_LOOKBACK = 48
CLUSTER_MIN_SOURCES = 2
MODEL = "claude-sonnet-4-6"
DATA_FILE = "stories.json"

# FRED economic data series — real indicators for overlay context
# Free data from Federal Reserve Economic Data. Each key is a display name,
# each value is the FRED series ID. To fetch, the scraper uses fetch_fred(series_id).
FRED_SERIES = {
    "unemployment_rate":  "UNRATE",       # US unemployment %
    "cpi_inflation":      "CPIAUCSL",     # Consumer Price Index (inflation)
    "fed_funds_rate":     "DFF",          # Federal funds rate
    "10yr_treasury":      "DGS10",        # 10-year treasury yield
    "30yr_mortgage":      "MORTGAGE30US", # 30-year mortgage rate
    "home_price_index":   "CSUSHPISA",    # Case-Shiller home prices
    "oil_price_wti":      "DCOILWTICO",   # WTI crude oil $/barrel
    "dollar_index":       "DTWEXBGS",     # Trade-weighted USD index
    "vix":                "VIXCLS",       # CBOE volatility index
    "gold_price":         "GOLDAMGBD228NLBM",  # London gold fix
    "consumer_sentiment": "UMCSENT",      # U Michigan consumer sentiment
    "manufacturing_pmi":  "NAPM",         # Manufacturing activity index
}

# Global state tracking for /status endpoint
last_run = {
    "time": None,
    "stories": 0,
    "articles": 0,
    "status": "not_yet_run"
}

RSS_FEEDS = [
    # ── Tier 1: Wire services ──────────────────────────────────────
    {"url": "https://feeds.reuters.com/reuters/topNews",          "source": "Reuters",        "lean": "centre"},
    {"url": "https://apnews.com/rss",                             "source": "AP",             "lean": "centre"},
    {"url": "https://www.afp.com/en/rss",                         "source": "AFP",            "lean": "centre"},

    # ── Tier 2: Western broadcast / quality press ──────────────────
    {"url": "https://www.bbc.com/news/world/rss.xml",             "source": "BBC",            "lean": "centre"},
    {"url": "https://rss.dw.com/rdf/rss-en-world",                "source": "DW",             "lean": "centre"},
    {"url": "https://www.theguardian.com/world/rss",              "source": "The Guardian",   "lean": "centre-left"},
    {"url": "https://feeds.bloomberg.com/politics/news.rss",      "source": "Bloomberg",      "lean": "financial-centre"},
    {"url": "https://www.ft.com/world?format=rss",                "source": "FT",             "lean": "financial-centre"},

    # ── Global South / non-Western ─────────────────────────────────
    {"url": "https://www.aljazeera.com/xml/rss/all.xml",          "source": "Al Jazeera",     "lean": "centre-left"},
    {"url": "https://www.scmp.com/rss/91/feed",                   "source": "SCMP",           "lean": "china-hk"},
    {"url": "https://timesofindia.indiatimes.com/rss.cms",        "source": "Times of India", "lean": "indian-nationalist"},
    {"url": "https://www.theafricareport.com/feed/",              "source": "Africa Report",  "lean": "pan-african"},
    {"url": "https://www.dawn.com/feeds/home",                    "source": "Dawn",           "lean": "pakistan-press"},
    {"url": "https://english.alarabiya.net/rss.xml",              "source": "Al Arabiya",     "lean": "saudi-aligned"},
    {"url": "https://www.haaretz.com/cmlink/1.628765",            "source": "Haaretz",        "lean": "israel-left"},
    {"url": "https://www.middleeasteye.net/rss",                  "source": "Middle East Eye","lean": "centre-left"},

    # ── State-aligned (labelled) ───────────────────────────────────
    {"url": "https://tass.com/rss/v2.xml",                        "source": "TASS",           "lean": "russian-state"},
    {"url": "https://www.globaltimes.cn/rss/outbrain.xml",        "source": "Global Times",   "lean": "chinese-state"},
    {"url": "https://www.irna.ir/en/rss.xml",                     "source": "IRNA",           "lean": "iran-state"},
    {"url": "https://www.presstv.ir/RSS",                         "source": "PressTV",        "lean": "iran-state"},

    # ── Investigative / accountability ─────────────────────────────
    {"url": "https://bellingcat.com/feed",                        "source": "Bellingcat",     "lean": "investigative-osint"},
    {"url": "https://www.occrp.org/en/rss",                       "source": "OCCRP",          "lean": "investigative"},
    {"url": "https://theintercept.com/feed/?rss",                 "source": "The Intercept",  "lean": "left-investigative"},
    {"url": "https://www.propublica.org/feeds/propublica/main",   "source": "ProPublica",     "lean": "investigative"},
    {"url": "https://tbij.com/feed/",                             "source": "TBIJ",           "lean": "investigative"},  # Bureau of Investigative Journalism
    {"url": "https://www.correctiv.org/en/feed/",                 "source": "Correctiv",      "lean": "investigative"},  # German investigative
    {"url": "https://www.icij.org/feed/",                         "source": "ICIJ",           "lean": "investigative"},  # Panama Papers org
    {"url": "https://meduza.io/en/rss/all",                       "source": "Meduza",         "lean": "russia-critical"},

    # ── Specialist / think tanks ───────────────────────────────────
    {"url": "https://www.understandingwar.org/rss.xml",           "source": "ISW",            "lean": "nato-aligned"},
    {"url": "https://foreignpolicy.com/feed/",                    "source": "Foreign Policy", "lean": "us-foreign-policy"},
    {"url": "https://www.crisisgroup.org/rss.xml",                "source": "ICG",            "lean": "conflict-analysis"},  # International Crisis Group
    {"url": "https://www.stimson.org/feed/",                      "source": "Stimson Center", "lean": "analytical"},
    {"url": "https://carnegieendowment.org/rss/solr?query=*",     "source": "Carnegie",       "lean": "analytical"},
    {"url": "https://www.iiss.org/en/rss/",                       "source": "IISS",           "lean": "defence-analytical"},
    {"url": "https://www.chathamhouse.org/rss.xml",               "source": "Chatham House",  "lean": "uk-analytical"},
    {"url": "https://www.sipri.org/rss.xml",                      "source": "SIPRI",          "lean": "arms-research"},  # Stockholm peace research

    # ── Regional specialists ───────────────────────────────────────
    {"url": "https://sudanwarmonitor.com/feed/",                  "source": "Sudan War Monitor",      "lean": "conflict-data"},
    {"url": "https://www.ethiopia-insight.com/feed/",             "source": "Ethiopia Insight",       "lean": "regional-specialist"},
    {"url": "https://www.afghanistan-analysts.org/en/feed/",      "source": "Afghanistan Analysts",   "lean": "analytical"},
    {"url": "https://syriadirect.org/feed/",                      "source": "Syria Direct",           "lean": "regional-specialist"},
    {"url": "https://www.irannewswire.org/rss",                   "source": "Iran News Wire",         "lean": "iran-opposition"},
    {"url": "https://iranwire.com/en/feed/",                      "source": "IranWire",               "lean": "iran-independent"},
    {"url": "https://www.jpost.com/Rss/RssFeedsHeadlines.aspx",   "source": "Jerusalem Post",         "lean": "israel-centre"},
    {"url": "https://balkaninsight.com/feed/",                    "source": "BIRN",                   "lean": "investigative"},  # Balkan Investigative Reporting

    # ── Financial intelligence ─────────────────────────────────────
    {"url": "https://home.treasury.gov/system/files/126/ofac.xml","source": "OFAC",           "lean": "us-government"},  # Sanctions
    {"url": "https://www.worldbank.org/en/news/all?format=rss",   "source": "World Bank",     "lean": "multilateral"},
    {"url": "https://www.imf.org/en/News/Rss?language=eng",       "source": "IMF",            "lean": "multilateral"},

    # ── Tier 0: Primary documents / official data (facts not narratives) ──
    {"url": "https://press.un.org/en/rss.xml",                          "source": "UN Press",         "lean": "primary-document"},
    {"url": "https://www.icc-cpi.int/rss/press-releases",               "source": "ICC",              "lean": "primary-document"},
    {"url": "https://www.iaea.org/newscenter/pressreleases/rss",        "source": "IAEA",             "lean": "primary-document"},
    {"url": "https://www.ohchr.org/EN/NewsEvents/Pages/RSSFeeds.aspx",  "source": "OHCHR",            "lean": "primary-document"},
    {"url": "https://home.treasury.gov/system/files/126/ofac.xml",      "source": "OFAC",             "lean": "primary-document"},  # sanctions
    {"url": "https://www.sipri.org/rss.xml",                            "source": "SIPRI",            "lean": "primary-document"},  # arms data
    {"url": "https://www.opensanctions.org/feed.rss",                   "source": "OpenSanctions",    "lean": "primary-document"},
    {"url": "https://sanctionsmap.eu/api/v1/rss",                       "source": "EU Sanctions Map", "lean": "primary-document"},
    {"url": "https://www.fatf-gafi.org/en/publications/rss.xml",        "source": "FATF",             "lean": "primary-document"},  # financial crime
    {"url": "https://www.icij.org/feed/",                               "source": "ICIJ",             "lean": "primary-document"},  # document leaks
    {"url": "https://acleddata.com/feed/",                              "source": "ACLED",            "lean": "primary-document"},  # conflict events
    {"url": "https://reliefweb.int/updates/rss.xml",                    "source": "ReliefWeb",        "lean": "primary-document"},

    # ── B-grade independent journalists (checked vs intel/primary only) ──
    # US national security / intelligence
    {"url": "https://seymourhersh.substack.com/feed",             "source": "Seymour Hersh",   "lean": "independent"},
    {"url": "https://www.emptywheel.net/feed/",                   "source": "Emptywheel",      "lean": "independent"},   # Marcy Wheeler — legal/intel
    {"url": "https://kenklippenstein.substack.com/feed",          "source": "Ken Klippenstein","lean": "independent"},   # leaked US gov docs
    {"url": "https://leefang.substack.com/feed",                  "source": "Lee Fang",        "lean": "independent"},   # corporate/lobbying
    {"url": "https://thedeadhand.substack.com/feed",              "source": "The Dead Hand",   "lean": "independent"},   # nuclear/arms control
    # Russia / Eastern Europe
    {"url": "https://johnhelmer.net/feed/",                       "source": "John Helmer",     "lean": "independent"},   # Russia oligarchs
    {"url": "https://www.craigmurray.org.uk/feed/",               "source": "Craig Murray",    "lean": "independent"},   # former UK ambassador
    {"url": "https://consortiumnews.com/feed/",                   "source": "Consortium News", "lean": "independent"},   # ex-CIA/intel writers
    # Middle East / conflict fieldwork
    {"url": "https://lindsey-snell.ghost.io/rss/",                "source": "Lindsey Snell",   "lean": "independent"},   # Syria/Iran field
    {"url": "https://richardmedhurst.substack.com/feed",          "source": "Richard Medhurst","lean": "independent"},   # UK/Middle East
    {"url": "https://electronicintifada.net/rss.xml",             "source": "Electronic Intifada","lean": "independent"}, # Palestine primary source
    # OSINT specialists (individual accounts)
    {"url": "https://blackbirdgroup.substack.com/feed",           "source": "Black Bird Group","lean": "osint"},          # Pasi Paroinen — Baltic
    {"url": "https://navalgazing.net/feed",                       "source": "Naval Gazing",    "lean": "osint"},          # naval / shipping OSINT
    # Financial / corporate intelligence
    {"url": "https://www.globalwitness.org/en/press-releases/rss/","source": "Global Witness", "lean": "independent"},   # resource corruption
    {"url": "https://www.followthemoney.eu/en/rss",               "source": "Follow the Money","lean": "independent"},   # Dutch financial crime
    {"url": "https://www.organized-crime.nl/feed/",               "source": "OCCRP Netherlands","lean": "independent"},
    # Humanitarian/conflict ground-truth
    {"url": "https://www.msf.org/en/news/rss",                    "source": "MSF",             "lean": "primary-document"}, # Doctors Without Borders
    {"url": "https://www.amnesty.org/en/latest/news/feed/",       "source": "Amnesty",         "lean": "independent"},

    # ── Humanitarian / conflict data ──────────────────────────────
    {"url": "https://reliefweb.int/updates/rss.xml",              "source": "ReliefWeb",      "lean": "humanitarian"},
    {"url": "https://www.hrw.org/rss",                            "source": "HRW",            "lean": "human-rights"},
    {"url": "https://acleddata.com/feed/",                        "source": "ACLED",          "lean": "conflict-data"},
    {"url": "https://www.amnesty.org/en/latest/news/feed/",       "source": "Amnesty",        "lean": "human-rights"},
    {"url": "https://msf.org/en/news/rss",                        "source": "MSF",            "lean": "humanitarian"},  # Doctors Without Borders
    {"url": "https://www.savethechildren.net/rss.xml",            "source": "Save the Children","lean": "humanitarian"},
]

GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"
# ─────────────────────────────────────────────
# SOURCE TIER SYSTEM
# ─────────────────────────────────────────────
SOURCE_TIERS = {
    # ── Tier 0: Primary documents (facts, not narratives) ─────────
    # Institutional mandate creates bias but the DATA is primary evidence.
    # Court filings, inspection results, sanctions designations, conflict data.
    "IAEA": 0, "ICC": 0, "OHCHR": 0, "UN Press": 0,
    "OFAC": 0, "ACLED": 0, "SIPRI": 0, "ICIJ": 0,
    "OpenSanctions": 0, "EU Sanctions Map": 0, "FATF": 0,
    "MSF": 0, "ReliefWeb": 0, "HRW": 0, "Amnesty": 0,

    # ── Tier 1: Wire services (independent news confirmation) ──────
    # Cleanest news confirmation layer. NOT truth arbiters —
    # they confirm that events happened, not what they mean.
    "Reuters": 1, "AP": 1, "AFP": 1,

    # ── Tier 2: Independent intel / OSINT / investigative ─────────
    # Reproducible methodology, disclosed funding, not mainstream press.
    # These are the corroboration layer above wire.
    "Bellingcat": 2, "OCCRP": 2, "TBIJ": 2, "ProPublica": 2,
    "Correctiv": 2, "BIRN": 2, "Global Witness": 2,
    "Follow the Money": 2, "ISW": 2, "ICG": 2, "IISS": 2,
    "Carnegie": 2, "Stimson Center": 2,
    "Sudan War Monitor": 2, "Syria Direct": 2,
    "IranWire": 2, "Iran News Wire": 2, "Ethiopia Insight": 2,
    "Afghanistan Analysts": 2, "Meduza": 2,
    "GeoConfirmed": 2, "Aurora Intel": 2, "Conflict Monitor": 2,
    "Black Bird Group": 2, "Naval Gazing": 2,
    "Seymour Hersh": 2, "Emptywheel": 2, "Ken Klippenstein": 2,
    "Lee Fang": 2, "Craig Murray": 2, "John Helmer": 2,
    "Lindsey Snell": 2, "Consortium News": 2, "Electronic Intifada": 2,
    "Sanctions Radar": 2,
    "Bluesky/bellingcat": 2, "Bluesky/emptywheel": 2,

    # ── Tier 3: Mainstream press (coverage, not verification) ──────
    # Concentrated ownership — tracked for coverage gaps and framing.
    # Used to note what mainstream IS or ISN'T covering.
    # NEVER used to verify claims.
    "BBC": 3, "DW": 3, "The Guardian": 3, "Bloomberg": 3, "FT": 3,
    "Al Jazeera": 3, "SCMP": 3, "Times of India": 3, "Africa Report": 3,
    "Dawn": 3, "Haaretz": 3, "Middle East Eye": 3, "Al Arabiya": 3,
    "Jerusalem Post": 3, "Foreign Policy": 3, "The Intercept": 3,
    "IMF": 3, "World Bank": 3,  # institutional advocacy, not primary data
    "Chatham House": 3,          # UK establishment-adjacent
    "Bluesky/nahaltoosi": 3, "Bluesky/laraseligman": 3,

    # ── Tier 4: State-aligned / state media ───────────────────────
    "TASS": 4, "Global Times": 4, "IRNA": 4, "PressTV": 4,
    "RT": 4, "Sputnik": 4, "CGTN": 4,

    # ── Tier 5: Social media ──────────────────────────────────────
    "Reddit": 5, "Telegram": 5, "Bluesky": 5,
}

def get_source_tier(source_name):
    """
    Returns tier 0-5. Lower = more epistemically reliable.
    Tier 0: primary documents (IAEA, ICC, OFAC, ACLED etc)
    Tier 1: wire services (Reuters, AP, AFP)
    Tier 2: independent intel/OSINT/investigative
    Tier 3: mainstream press (coverage tracking only, not verification)
    Tier 4: state media
    Tier 5: social media
    """
    for key, tier in SOURCE_TIERS.items():
        if key.lower() in source_name.lower():
            return tier
    if "reddit" in source_name.lower():   return 5
    if "telegram" in source_name.lower(): return 5
    if "bluesky" in source_name.lower():  return 5
    # Default: treat unknown sources as mainstream-equivalent (tier 3)
    return 3

# ── Intelligence-grade source classification ──────────────────
# Sources that provide corroboration above social/unverified level.
# Tier 1-2: wire/quality press (already in SOURCE_TIERS)
# Intel tier: OSINT verification orgs, investigative journalism, think tanks,
#             primary document publishers — these independently confirm facts
#             through different methodologies than wire services


# ═══════════════════════════════════════════════════════════════════
# ACTOR INTEREST DATABASE
# For each major actor: what they structurally benefit from,
# what narratives serve them, what they lose if truth prevails,
# and what their known information operations look like.
# This is referenced when Claude analyses "why would X say this."
# ═══════════════════════════════════════════════════════════════════

ACTOR_INTERESTS = {
    # ── United States (government/deep state) ─────────────────────
    "United States": {
        "structural_interests": [
            "Dollar hegemony and SWIFT dominance",
            "NATO expansion and forward military presence",
            "Access to energy corridors and chokepoints",
            "Preventing peer competitors (China, Russia) from regional dominance",
            "Arms industry revenue — $800B+ annual defence budget",
        ],
        "narrative_tools": [
            "Framing adversary actions as unprovoked aggression",
            "Human rights rhetoric to justify sanctions/intervention",
            "Democracy promotion framing for geopolitical objectives",
            "Classification to suppress embarrassing primary documents",
            "Embedding journalists in military units (narrative shaping)",
        ],
        "loses_if_true": {
            "Iraq WMD fabrication": "legitimacy of intelligence community",
            "NSA mass surveillance": "rule-of-law credibility",
            "CIA regime change ops": "democracy promotion credibility",
            "Ukraine biolabs narrative": "unclear — few primary docs",
        },
        "known_disinfo_ops": ["Operation Mockingbird (historical)", "Rewards for Justice (current)", "GEC counter-disinfo programmes"],
        "financial_beneficiaries": ["Raytheon", "Lockheed Martin", "Boeing Defense", "General Dynamics", "Northrop Grumman"],
    },

    # ── Russia ─────────────────────────────────────────────────────
    "Russia": {
        "structural_interests": [
            "Buffer states on western border — NATO exclusion zone",
            "Gas pipeline revenue and European energy dependence",
            "Black Sea and Mediterranean naval access",
            "Preventing ICC prosecution of senior officials",
            "Domestic legitimacy narrative — great power restoration",
        ],
        "narrative_tools": [
            "NATO expansion as existential threat framing",
            "Denazification/genocide framing for Ukraine war",
            "Western media as propaganda weapon (to undermine credibility)",
            "Amplifying Western contradictions and hypocrisy",
            "RT/TASS/Sputnik for direct narrative projection",
            "Doppelganger operation (cloned Western news sites)",
        ],
        "loses_if_true": {
            "MH17 downing": "full ICC and international liability",
            "Bucha massacre": "war crimes prosecution chain",
            "Navalny assassination": "direct Kremlin order chain",
            "Nord Stream sabotage": "who actually did it — contested",
        },
        "known_disinfo_ops": ["Doppelganger (EU DisinfoLab documented)", "Secondary Infektion", "GRU Unit 29155 active measures", "Internet Research Agency (troll farms)"],
        "financial_beneficiaries": ["Gazprom", "Rosneft", "Rostec (arms)", "Wagner/Africa Corps successors", "Russian oligarch network (Rotenberg, Sechin, Kovalchuk)"],
    },

    # ── China ──────────────────────────────────────────────────────
    "China": {
        "structural_interests": [
            "Taiwan reunification — CCP legitimacy depends on it",
            "South China Sea control — 40% of global trade",
            "Belt and Road debt leverage over developing nations",
            "Technology decoupling prevention — semiconductor access",
            "Iran as oil supplier — 90% of Iran oil exports to China",
            "Undermining USD hegemony via yuan internationalisation",
        ],
        "narrative_tools": [
            "Non-interference in internal affairs (protects own abuses)",
            "Multipolar world framing (legitimises US competitor bloc)",
            "Wolf Warrior diplomacy (aggressive push-back on criticism)",
            "Global Times/Xinhua/CGTN for international narrative",
            "Amplifying US racial violence and political dysfunction",
        ],
        "loses_if_true": {
            "Uyghur detention scale": "genocide designation, sanctions",
            "COVID lab origin": "international liability, reparations",
            "BRI debt trap details": "developing world alignment shifts",
            "Fentanyl precursor supply": "direct diplomatic consequences",
        },
        "known_disinfo_ops": ["Spamouflage (Meta/EU documented)", "Influence ops via TikTok algorithm (alleged)", "Confucius Institute soft power network"],
        "financial_beneficiaries": ["CNOOC", "Sinopec", "Huawei", "SMIC", "PLA industrial complex", "SOE network"],
    },

    # ── Iran ───────────────────────────────────────────────────────
    "Iran": {
        "structural_interests": [
            "Nuclear programme as deterrent and regional leverage",
            "Proxy network (Hezbollah, Houthis, Shia militias) as strategic depth",
            "Sanctions relief — economy at critical stress point",
            "Hormuz control as ultimate leverage card",
            "Regime survival against domestic opposition",
            "Preventing Israeli normalisation with Arab states",
        ],
        "narrative_tools": [
            "Anti-colonial resistance framing for regional actions",
            "Islamic solidarity framing for proxy network",
            "Nuclear programme as peaceful civilian use",
            "IRGC operations deniability via proxies",
            "IRNA/PressTV for state narrative",
        ],
        "loses_if_true": {
            "84% enrichment": "weapons programme, not civilian",
            "Proxy weapons supply chains": "direct attribution of attacks",
            "IRGC command of Oct 7 planning": "state actor designation",
            "Evasion of sanctions via shadow fleet": "secondary sanctions on partners",
        },
        "known_disinfo_ops": ["Influence ops targeting US elections (FBI/ODNI documented)", "Hackers-for-hire network", "Front media sites in Middle East"],
        "financial_beneficiaries": ["IRGC economic empire (40% of economy)", "Bonyads (revolutionary foundations)", "Shamkhani oil network (OFAC sanctioned Apr 2026)"],
    },

    # ── Israel ─────────────────────────────────────────────────────
    "Israel": {
        "structural_interests": [
            "Preventing Iranian nuclear capability — existential framing",
            "Abraham Accords expansion — Arab normalisation",
            "US military and diplomatic support maintenance",
            "Preventing ICC jurisdiction over senior officials",
            "Palestinian Authority weakness — no state solution",
            "West Bank settlements — irreversible facts on ground",
        ],
        "narrative_tools": [
            "October 7 as existential event framing (accurate but also deployed politically)",
            "Hamas = ISIS equivalence framing",
            "Human shields claims to delegitimise civilian death data",
            "Antisemitism accusations to suppress criticism",
            "Security necessity framing for civilian infrastructure strikes",
        ],
        "loses_if_true": {
            "ICJ genocide provisional measures": "international isolation",
            "Deir Yassin/Tantura historical massacres": "founding narrative damage",
            "Settler violence documentation": "US political pressure",
            "Al-Ahli hospital incident": "still contested — both sides claim",
        },
        "known_disinfo_ops": ["Unit 8200 (cyber/signals)", "IDF Spokesperson narrative management", "Hasbara coordination network", "Targeting of journalists (CPJ documents 130+ killed in Gaza)"],
        "financial_beneficiaries": ["Elbit Systems", "Rafael Advanced Defense", "IAI", "US military aid ($3.8B annual)", "Settlements movement (Yesha Council)"],
    },

    # ── Donald Trump ───────────────────────────────────────────────
    "Donald Trump": {
        "structural_interests": [
            "Personal legal protection — presidential immunity",
            "Truth Social and media empire revenue",
            "Real estate empire deregulation",
            "Tariff policy as political leverage and revenue",
            "Weakening international institutions that constrain US action",
            "Base mobilisation via constant conflict framing",
        ],
        "narrative_tools": [
            "Fake news framing to delegitimise critical coverage",
            "Deep state narrative to explain opposition",
            "Deal-making framing for all foreign policy",
            "Strength/weakness binary to justify aggression",
            "Truth Social as unfiltered channel bypassing press",
        ],
        "loses_if_true": {
            "January 6 coordination evidence": "criminal liability",
            "Trump Org financial fraud": "already convicted in NY",
            "Russia 2016 coordination": "contested — Mueller partial findings",
            "Iran deal break motivations": "Netanyahu relationship, Adelson money",
        },
        "financial_beneficiaries": ["Trump Organization", "Truth Social (DJT stock)", "Trump Media & Technology Group", "Mar-a-Lago", "Saudi golf partnership (LIV)"],
    },

    # ── Saudi Arabia ───────────────────────────────────────────────
    "Saudi Arabia": {
        "structural_interests": [
            "Oil price above $70/barrel (Vision 2030 requires it)",
            "Iran containment — sectarian and geopolitical",
            "US security umbrella maintenance",
            "MBS succession consolidation — no rival power centres",
            "Normalisation with Israel (for US security guarantees)",
            "OPEC+ production discipline",
        ],
        "narrative_tools": [
            "Reformist modernisation framing (Vision 2030)",
            "Iran as regional destabiliser",
            "Yemen war as defensive operation",
            "Sportswashing — LIV Golf, Newcastle, F1",
        ],
        "loses_if_true": {
            "MBS ordered Khashoggi killing": "already admitted indirectly, ICC referral stalled",
            "Saudi 9/11 connections": "28 pages — some declassified",
            "Yemen civilian targeting": "UNHRC documented",
        },
        "financial_beneficiaries": ["Saudi Aramco", "PIF (sovereign wealth fund)", "MBS personal network", "US arms manufacturers ($110B+ deals)"],
    },

    # ── Ukraine ────────────────────────────────────────────────────
    "Ukraine": {
        "structural_interests": [
            "Western military and financial support continuation",
            "NATO membership as ultimate security guarantee",
            "Territorial integrity — internationally recognised borders",
            "War crimes accountability for Russia",
            "Preventing frozen conflict that legitimises occupation",
        ],
        "narrative_tools": [
            "Civilian casualty emphasis to maintain Western support",
            "Russian atrocity documentation (genuine but also strategic)",
            "NATO membership framing as non-negotiable",
            "Zelensky as democratic hero narrative",
            "Any peace deal as Russian victory framing",
        ],
        "loses_if_true": {
            "Ukrainian corruption levels": "Western aid scrutiny",
            "Azov battalion history": "narrative complexity for Western audiences",
            "Civilian shield accusations": "Russian claims — limited primary doc evidence",
        },
        "financial_beneficiaries": ["Zelensky's inner circle (corruption allegations)", "Western defence industry (weapons contracts)", "Reconstruction contracts (postwar)"],
    },
}

def get_actor_context(actor_name):
    """
    Returns structural interests and narrative tools for a named actor.
    Used to pre-load Claude with 'why would X say this' context.
    Fuzzy match — checks if actor_name contains any key.
    """
    actor_name_lower = actor_name.lower()
    for key, data in ACTOR_INTERESTS.items():
        if key.lower() in actor_name_lower or actor_name_lower in key.lower():
            return key, data
    return None, None

def build_actor_context_block(cluster_articles):
    """
    Scan article entities for known actors and build a context block
    explaining their structural interests to Claude.
    Returns a string injected into the accuracy_context.
    """
    # Collect all named entities from articles
    all_text = " ".join(
        (a.get("title","") + " " + (a.get("body","") or a.get("summary","")))
        for a in cluster_articles
    )
    
    found_actors = {}
    for actor_name, data in ACTOR_INTERESTS.items():
        if actor_name.lower() in all_text.lower():
            found_actors[actor_name] = data
    
    if not found_actors:
        return ""
    
    lines = ["ACTOR STRUCTURAL INTERESTS (why each actor would say what they say):"]
    for actor, data in list(found_actors.items())[:4]:  # max 4 actors
        interests = data.get("structural_interests", [])[:3]
        narrative_tools = data.get("narrative_tools", [])[:2]
        beneficiaries = data.get("financial_beneficiaries", [])[:3]
        lines.append(f"  {actor.upper()}:")
        lines.append(f"    Core interests: {'; '.join(interests)}")
        lines.append(f"    Narrative tools: {'; '.join(narrative_tools)}")
        lines.append(f"    Financial beneficiaries: {', '.join(beneficiaries)}")
    
    lines.append(
        "INSTRUCTION: For each claim in the articles, identify which actor made it, "
        "what structural interest it serves, and whether the claim fits their known "
        "narrative playbook. Surface this in who_benefits and narrative_analysis."
    )
    return "\n".join(lines)


# ── Tier 0: Primary documents — highest epistemic value ─────────
# These are facts, not journalism. Institutional mandate creates bias
# but the data itself (a sanction designation, an IAEA inspection result,
# a court filing) is verifiable primary evidence.
PRIMARY_SOURCES = {
    "IAEA", "ICC", "OHCHR", "UN Press", "OFAC", "ACLED",
    "SIPRI", "OpenSanctions", "EU Sanctions Map", "FATF",
    "ICIJ",        # primary leaked documents
    "MSF",         # field medical data
    "ReliefWeb",   # humanitarian field data
    "HRW",         # field human rights documentation
    "Amnesty",     # field human rights documentation
}

# ── Tier 1: Intel-grade independent sources ──────────────────────
# These verify through independent methodology (geolocation,
# document analysis, on-ground fieldwork, financial tracing).
# Funding is disclosed. Methodology is published.
# These are NOT mainstream press. Do NOT conflate.
INTEL_SOURCES = {
    # ── OSINT / geolocation verification ─────────────────────────
    "Bellingcat", "GeoConfirmed", "Aurora Intel", "Conflict Monitor",
    "DeepState", "Black Bird Group", "Naval Gazing",
    # ── Investigative / financial crime ──────────────────────────
    "OCCRP", "TBIJ", "ProPublica", "Correctiv", "BIRN",
    "Global Witness", "Follow the Money", "OCCRP Netherlands",
    # ── Regional specialists (primary access, not wire repackaging) ─
    "Sudan War Monitor", "Syria Direct", "IranWire", "Iran News Wire",
    "Ethiopia Insight", "Afghanistan Analysts",
    # ── Think tanks (analytical, not advocacy) ────────────────────
    "ISW", "ICG", "IISS", "Carnegie", "Stimson Center",
    "Chatham House",  # note: UK establishment-adjacent — declare
    # ── B-grade independent journalists ──────────────────────────
    # Verified via primary docs / OSINT — NOT via mainstream press
    "Seymour Hersh", "Emptywheel", "Ken Klippenstein",
    "Lee Fang", "Craig Murray", "John Helmer", "Lindsey Snell",
    "Richard Medhurst", "Consortium News", "Electronic Intifada",
    "The Dead Hand", "Meduza",
    # ── Sanctions / financial intelligence ────────────────────────
    "Sanctions Radar",
}

# State media — present but must not count as corroboration
STATE_SOURCES = {
    "TASS", "Xinhua", "Global Times", "IRNA", "PressTV",
    "RT", "Sputnik", "CGTN", "Press TV",
}

def cluster_has_wire_source(cluster):
    """True if any tier-1 wire service (Reuters/AP/AFP) is in the cluster."""
    return any(get_source_tier(a["source"]) == 1 for a in cluster)

def cluster_has_primary_source(cluster):
    """True if any tier-0 primary document source is in the cluster."""
    return any(get_source_tier(a["source"]) == 0 for a in cluster)

def cluster_has_intel_corroboration(cluster):
    """
    True if any tier-2 independent intel source is present.
    This includes OSINT, investigative journalism, and B-grade
    independent journalists — all checked against primary docs only.
    """
    return any(get_source_tier(a["source"]) <= 2 for a in cluster)

def cluster_corroboration_detail(cluster):
    """
    Corroboration using a three-tier hierarchy:
      Tier 0 — Primary documents (IAEA, ICC, OFAC, ACLED, ICIJ, MSF...)
               These are facts, not narratives. Highest epistemic value.
      Tier 1 — Intel-grade independent (Bellingcat, OCCRP, ISW, specialists,
               B-grade independent journalists verified by primary docs)
               These use reproducible methodology and disclosed funding.
      Wire    — Reuters/AP/AFP as news confirmation layer (NOT the truth arbiter)
      State   — Government narrative — flags divergence, not corroboration

    KEY DESIGN PRINCIPLE: mainstream press (BBC, Guardian, Bloomberg etc.)
    is NOT used as a corroboration source. It carries packed narratives from
    concentrated ownership. We note wire service coverage separately.
    Verification flows: claim → Tier 0 → Tier 1 → wire (optional confirmation)
    Never: claim → mainstream → call it verified.
    """
    primary_srcs = []
    intel_srcs   = []
    wire_srcs    = []
    social_srcs  = []
    state_srcs   = []
    mainstream_srcs = []  # tracked but not used for corroboration

    # Mainstream outlets with known ownership concentration
    MAINSTREAM = {
        "BBC", "DW", "Bloomberg", "FT", "The Guardian", "Al Jazeera",
        "SCMP", "Times of India", "Al Arabiya", "Haaretz", "Jerusalem Post",
        "Middle East Eye", "Africa Report", "Dawn", "Foreign Policy",
        "CNN", "NYT", "Washington Post", "Fox", "Politico", "The Atlantic",
    }

    for a in cluster:
        src  = a["source"]
        tier = get_source_tier(src)

        # Check Primary Sources first (highest)
        if any(ps.lower() in src.lower() for ps in PRIMARY_SOURCES):
            primary_srcs.append(src)
        # Check Intel Sources
        elif any(intel.lower() in src.lower() for intel in INTEL_SOURCES):
            intel_srcs.append(src)
        # Wire services (Reuters/AP/AFP — most independent wires)
        elif tier == 1:
            wire_srcs.append(src)
        # State media
        elif tier == 4 or any(st.lower() in src.lower() for st in STATE_SOURCES):
            state_srcs.append(src)
        # Social
        elif tier == 5:
            social_srcs.append(src)
        # Mainstream press — track but don't use for verification
        elif any(ms.lower() in src.lower() for ms in MAINSTREAM):
            mainstream_srcs.append(src)

    # Deduplicate
    primary_srcs    = list(dict.fromkeys(primary_srcs))
    intel_srcs      = list(dict.fromkeys(intel_srcs))
    wire_srcs       = list(dict.fromkeys(wire_srcs))
    social_srcs     = list(dict.fromkeys(social_srcs))
    state_srcs      = list(dict.fromkeys(state_srcs))
    mainstream_srcs = list(dict.fromkeys(mainstream_srcs))

    # ── Confidence based on Primary + Intel only ──────────────────
    # Wire serves as independent news confirmation, not truth arbiter
    # Mainstream is noted but never drives confidence upward

    independent_count = len(primary_srcs) + len(intel_srcs)

    if len(primary_srcs) >= 2:
        confidence  = "high"
        conf_reason = (f"Primary document corroboration: "
                      f"{', '.join(primary_srcs[:3])} — "
                      f"these are primary evidence, not journalism")
    elif len(primary_srcs) >= 1 and len(intel_srcs) >= 1:
        confidence  = "high"
        conf_reason = (f"Primary doc ({primary_srcs[0]}) + "
                      f"independent intel ({', '.join(intel_srcs[:2])}) confirm independently")
    elif len(primary_srcs) >= 1 and wire_srcs:
        confidence  = "high"
        conf_reason = (f"Primary document ({primary_srcs[0]}) + "
                      f"wire confirmation ({wire_srcs[0]})")
    elif len(intel_srcs) >= 3:
        confidence  = "medium"
        conf_reason = (f"Multi-intel corroboration: {', '.join(intel_srcs[:4])} — "
                      f"independent methodologies converge — no primary doc yet")
    elif len(intel_srcs) >= 2:
        confidence  = "medium"
        conf_reason = (f"Two independent intel sources: {', '.join(intel_srcs[:3])} — "
                      f"not yet primary-document confirmed")
    elif len(primary_srcs) == 1:
        confidence  = "medium"
        conf_reason = (f"Single primary source ({primary_srcs[0]}) — "
                      f"high-quality evidence but needs corroboration")
    elif len(intel_srcs) == 1 and wire_srcs:
        confidence  = "medium"
        conf_reason = (f"Intel source ({intel_srcs[0]}) + wire confirmation ({wire_srcs[0]}) — "
                      f"no primary document yet")
    elif len(intel_srcs) == 1:
        confidence  = "low"
        conf_reason = (f"Single intel source ({intel_srcs[0]}) — "
                      f"no primary document or additional independent corroboration")
    elif wire_srcs and not intel_srcs and not primary_srcs:
        confidence  = "low"
        conf_reason = (f"Wire only ({', '.join(wire_srcs[:2])}) — "
                      f"news confirmed but no independent intel or primary doc verification")
    elif state_srcs and not primary_srcs and not intel_srcs:
        confidence  = "low"
        conf_reason = (f"State media only ({', '.join(state_srcs[:2])}) — "
                      f"official claim, not independently verified fact")
    elif social_srcs and not primary_srcs and not intel_srcs:
        confidence  = "low"
        conf_reason = f"Social signals only — unverified"
    else:
        confidence  = "low"
        conf_reason = "No primary document or independent intel corroboration"

    return {
        "confidence":        confidence,
        "conf_reason":       conf_reason,
        "primary_srcs":      primary_srcs,
        "intel_srcs":        intel_srcs,
        "wire_srcs":         wire_srcs,
        "social_srcs":       social_srcs,
        "state_srcs":        state_srcs,
        "mainstream_srcs":   mainstream_srcs,
        "has_primary":       bool(primary_srcs),
        "has_intel":         bool(intel_srcs),
        "has_wire":          bool(wire_srcs),
        "has_state":         bool(state_srcs),
        "has_social":        bool(social_srcs),
        "corroboration_count": independent_count,
    }

def cluster_source_diversity(cluster):
    """
    Diversity score 0-100. Rewards genuine perspective diversity:
    wire + intel + non-Western + opposing-political-alignment.
    Penalises: wire + state amplification (not real diversity).
    """
    detail = cluster_corroboration_detail(cluster)
    sources = {a["source"] for a in cluster}
    tiers   = {get_source_tier(a["source"]) for a in cluster}
    score   = 0

    # Wire presence
    if detail["wire_srcs"]: score += 25
    # Intel corroboration (independent of wire)
    if detail["intel_srcs"]: score += 25
    # Multiple independent sources (not same org family)
    if detail["corroboration_count"] >= 3: score += 20
    # Non-Western perspective present (genuine global view)
    non_western = {"Al Jazeera","SCMP","Times of India","Africa Report",
                   "Dawn","Middle East Eye","Al Arabiya","Haaretz","IRNA"}
    if any(nw.lower() in s.lower() for s in sources for nw in non_western): score += 15
    # State media WITHOUT wire to contradict it = NOT a diversity win
    # State media WITH wire = shows the gap = genuine signal
    if detail["state_srcs"] and detail["wire_srcs"]: score += 15
    # Penalty: state-only "diversity" (it's not diversity, it's one narrative)
    if detail["state_srcs"] and not detail["wire_srcs"] and not detail["intel_srcs"]:
        score = max(0, score - 20)

    return min(score, 100)
def is_provisional(article, hours=2):
    """
    Returns True if an article was published within the last N hours.
    Provisional articles are flagged as potentially unverified —
    breaking reports are often corrected within the first 2 hours.
    """
    try:
        from datetime import datetime as dt_cls
        pub = article.get("published","")
        if not pub: return False
        pub_dt = dt_cls.fromisoformat(pub.replace("Z","+00:00"))
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        age = (utc_now() - pub_dt).total_seconds() / 3600
        return age < hours
    except Exception:
        return False

def cluster_provisional_ratio(cluster):
    """What fraction of articles in this cluster are <2 hours old."""
    if not cluster: return 0
    prov = sum(1 for a in cluster if is_provisional(a))
    return prov / len(cluster)

def fetch_url(url, timeout=12):
    try:
        req = Request(url, headers={"User-Agent": "Parallax/1.0"})
        with urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  fetch error {url[:55]}: {e}")
        return None

def story_id(text):
    return hashlib.md5(text.encode()).hexdigest()[:8]

def utc_now():
    return datetime.now(timezone.utc)

def parse_date(s):
    if not s: return utc_now()
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"]:
        try: return datetime.strptime(s.strip(), fmt).replace(tzinfo=timezone.utc)
        except: pass
    return utc_now()

# ─────────────────────────────────────────────
# RSS
# ─────────────────────────────────────────────
def fetch_rss(feed):
    """
    Fetch RSS feed and extract ALL available metadata from each item.
    Captures: title, description, full content (if atom:content),
    author/dc:creator, categories/tags, geo coordinates, media,
    update timestamps, and related article links.
    """
    xml = fetch_url(feed["url"])
    if not xml: return []
    items = []
    cutoff = utc_now() - timedelta(hours=HOURS_LOOKBACK)

    # XML namespace map for extended RSS formats
    NS = {
        "atom":    "http://www.w3.org/2005/Atom",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc":      "http://purl.org/dc/elements/1.1/",
        "geo":     "http://www.w3.org/2003/01/geo/wgs84_pos#",
        "media":   "http://search.yahoo.com/mrss/",
        "georss":  "http://www.georss.org/georss",
    }

    try:
        root = ET.fromstring(xml)
        all_items = (list(root.iter("item")) +
                     list(root.iter("{http://www.w3.org/2005/Atom}entry")))

        for item in all_items:
            def get(tag, default=""):
                """Try multiple namespace variants for a tag"""
                for ns_prefix, ns_uri in [("", ""), *NS.items()]:
                    val = (item.findtext(f"{{{ns_uri}}}{tag}") if ns_uri
                           else item.findtext(tag))
                    if val: return val.strip()
                return default

            title = (get("title") or get("title", "")).strip()
            if not title or len(title) < 10: continue

            # Description / summary
            desc = (get("description") or get("summary") or "")
            desc_clean = re.sub("<[^>]+>", "", desc).strip()

            # Full content — many quality feeds include this
            full_content = (
                item.findtext(f"{{{NS['content']}}}encoded") or
                item.findtext(f"{{{NS['atom']}}}content") or ""
            )
            full_content_clean = re.sub("<[^>]+>", "", full_content).strip()

            # Link
            link_el = item.find(f"{{{NS['atom']}}}link")
            link = (item.findtext("link") or
                    (link_el.get("href","") if link_el is not None else ""))

            # Publication date
            pub = (item.findtext("pubDate") or
                   item.findtext(f"{{{NS['atom']}}}published") or
                   item.findtext(f"{{{NS['atom']}}}updated") or "")
            pub_dt = parse_date(pub)
            if pub_dt < cutoff: continue

            # Update date (for correction detection)
            updated = (item.findtext(f"{{{NS['atom']}}}updated") or
                      item.findtext("lastBuildDate") or pub)

            # Author / byline (dc:creator or author)
            author = (item.findtext(f"{{{NS['dc']}}}creator") or
                     item.findtext("author") or
                     item.findtext(f"{{{NS['atom']}}}author/{{{NS['atom']}}}name") or "")

            # Categories / tags (multiple)
            categories = []
            for cat_el in item.findall("category"):
                if cat_el.text: categories.append(cat_el.text.strip())
            for cat_el in item.findall(f"{{{NS['atom']}}}category"):
                term = cat_el.get("term","")
                if term: categories.append(term)

            # Geographic coordinates
            geo_lat  = (item.findtext(f"{{{NS['geo']}}}lat") or
                       item.findtext(f"{{{NS['georss']}}}point","").split()[0] if
                       item.findtext(f"{{{NS['georss']}}}point") else "")
            geo_lon  = (item.findtext(f"{{{NS['geo']}}}long") or
                       (item.findtext(f"{{{NS['georss']}}}point","").split()[1]
                        if len((item.findtext(f"{{{NS['georss']}}}point") or "").split()) > 1 else ""))

            # Media thumbnail / image URL (for visual stories)
            media_url = ""
            for mel in item.iter(f"{{{NS['media']}}}thumbnail"):
                media_url = mel.get("url","")
                break
            for mel in item.iter(f"{{{NS['media']}}}content"):
                if not media_url: media_url = mel.get("url","")
                break

            # Use best available text body
            # Priority: full atom:content > content:encoded > description
            best_body = full_content_clean or desc_clean
            text_for_clustering = f"{title}. {(best_body)[:300]}"

            # Extract dollar amounts, percentages, numbers from description
            # (financial signals often in RSS snippets)
            financial_signals = re.findall(
                r'\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|trillion|bn|mn|tn))?|'
                r'[\d,]+(?:\.\d+)?%|'
                r'(?:million|billion|trillion)\s+(?:dollars|euros|pounds)',
                best_body[:500], re.IGNORECASE
            )

            items.append({
                "title":       title,
                "summary":     desc_clean[:600],       # longer than before
                "url":         link,
                "source":      feed["source"],
                "lean":        feed.get("lean",""),
                "published":   pub_dt.isoformat(),
                "updated":     updated,
                "author":      author,
                "categories":  categories[:5],
                "text":        text_for_clustering,
                "body":        full_content_clean[:1200] if full_content_clean else None,
                "entities":    "",                      # filled by enrich_articles()
                "geo_lat":     geo_lat,
                "geo_lon":     geo_lon,
                "media_url":   media_url,
                "financial_signals": financial_signals[:8],
                "platform":    "rss",
            })

    except Exception as e:
        print(f"  parse error {feed['source']}: {e}")
    return items


# ─────────────────────────────────────────────
# FULL ARTICLE BODY EXTRACTION
# ─────────────────────────────────────────────

def fetch_article_body(url, max_words=1200):
    """
    Fetch the full body text of an article from its URL.
    Tries newspaper4k first (best for news sites), then trafilatura as fallback.
    Returns a dict with text, authors, and a truncated flag.
    Returns None if both fail or URL is empty.
    """
    if not url or not url.startswith("http"):
        return None

    text = None
    authors = []

    # ── Attempt 1: newspaper4k ──────────────────────────────────────
    if NEWSPAPER4K:
        try:
            art = newspaper.Article(url, language="en", fetch_images=False)
            art.download()
            art.parse()
            body = (art.text or "").strip()
            if len(body) > 150:
                text = body
                authors = art.authors or []
        except Exception as e:
            pass  # Fall through to trafilatura

    # ── Attempt 2: trafilatura fallback ─────────────────────────────
    if not text and TRAFILATURA:
        try:
            raw = fetch_url(url, timeout=10)
            if raw:
                extracted = trafilatura.extract(
                    raw,
                    include_comments=False,
                    include_tables=False,
                    no_fallback=False
                )
                if extracted and len(extracted.strip()) > 150:
                    text = extracted.strip()
        except Exception as e:
            pass

    if not text:
        return None

    # ── Truncate to max_words to control Claude context ─────────────
    words = text.split()
    truncated = len(words) > max_words
    if truncated:
        text = " ".join(words[:max_words]) + "…"

    return {
        "text": text,
        "authors": authors,
        "word_count": min(len(words), max_words),
        "truncated": truncated
    }


def extract_entities(text):
    """
    Run spaCy NER on article text to extract named people, organisations,
    locations and dates. Returns a compact string for the Claude prompt.
    """
    if not SPACY or not text:
        return ""
    try:
        doc = NLP(text[:5000])  # Cap input to avoid slow processing
        entities = {}
        for ent in doc.ents:
            if ent.label_ in ("PERSON", "ORG", "GPE", "LOC", "EVENT"):
                label = ent.label_
                if label not in entities:
                    entities[label] = set()
                entities[label].add(ent.text.strip())

        if not entities:
            return ""

        label_names = {
            "PERSON": "People mentioned",
            "ORG":    "Organisations",
            "GPE":    "Locations",
            "LOC":    "Locations",
            "EVENT":  "Events"
        }
        parts = []
        for label, names in entities.items():
            if names:
                parts.append(f"{label_names[label]}: {', '.join(sorted(names)[:8])}")
        return "\n".join(parts)
    except Exception:
        return ""



# ─────────────────────────────────────────────
# REDDIT — via PRAW (official API, free)
# ─────────────────────────────────────────────
#
# Setup (one-time):
#   1. Go to https://www.reddit.com/prefs/apps
#   2. Click "Create App" → choose "script"
#   3. Add REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET,
#      REDDIT_USER_AGENT to Replit Secrets
#
# Key subreddits for intelligence value:
#   worldnews, geopolitics, CredibleDefense,
#   UkrainianConflict, IsraelPalestine, iran,
#   syriancivilwar, Sino, MiddleEastNews

REDDIT_SUBREDDITS = [
    # ── General / geopolitics ──────────────────────────────────────
    {"name": "worldnews",              "lean": "centre"},
    {"name": "geopolitics",            "lean": "analytical"},
    {"name": "CredibleDefense",        "lean": "defence-analytical"},
    {"name": "GlobalPowers",           "lean": "geopolitical"},
    {"name": "IntelligenceAnalysis",   "lean": "analytical"},

    # ── Active conflicts ───────────────────────────────────────────
    {"name": "UkrainianConflict",      "lean": "ukraine-focused"},
    {"name": "RussiaUkraineWar2022",   "lean": "mixed"},
    {"name": "iran",                   "lean": "mixed"},
    {"name": "IRIranPolitics",         "lean": "iran-focused"},
    {"name": "IsraelPalestine",        "lean": "contested"},
    {"name": "syriancivilwar",         "lean": "mixed"},
    {"name": "Sudan",                  "lean": "mixed"},
    {"name": "YemenCivilWar",          "lean": "mixed"},
    {"name": "AfghanistanConflict",    "lean": "mixed"},

    # ── Regional ──────────────────────────────────────────────────
    {"name": "MiddleEastNews",         "lean": "mixed"},
    {"name": "Sino",                   "lean": "china-critical"},
    {"name": "ChinaPolicy",            "lean": "analytical"},
    {"name": "SouthAsia",              "lean": "analytical"},
    {"name": "Africa",                 "lean": "mixed"},
    {"name": "europe",                 "lean": "mixed"},

    # ── Specialist ────────────────────────────────────────────────
    {"name": "OSINT",                  "lean": "investigative"},
    {"name": "nuclearweapons",         "lean": "analytical"},
    {"name": "sanctions",              "lean": "analytical"},
    {"name": "WayOfTheBern",           "lean": "left"},  # Breaks stories early
    {"name": "conspiracy",             "lean": "sceptical"},  # Pattern detection
    {"name": "PropagandaPosters",      "lean": "analytical"},  # Disinfo tracking
]

# Min score to include a post (filters low-quality posts)
REDDIT_MIN_SCORE   = 50
# Max posts per subreddit per cycle
REDDIT_MAX_POSTS   = 10

try:
    import praw
    PRAW_AVAILABLE = True
    print("PRAW available — Reddit module enabled")
except ImportError:
    PRAW_AVAILABLE = False
    print("praw not installed — Reddit disabled")
    print("  Install: pip install praw")


def fetch_reddit():
    """
    Pull top posts from intelligence-relevant subreddits.
    Returns articles in the same format as fetch_rss().
    Requires REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET,
    REDDIT_USER_AGENT in environment/secrets.
    """
    if not PRAW_AVAILABLE:
        return []

    client_id     = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent    = os.environ.get("REDDIT_USER_AGENT", "Parallax/1.0")

    if not client_id or not client_secret:
        print("  Reddit: REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set — skipping")
        return []

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
    except Exception as e:
        print(f"  Reddit auth error: {e}")
        return []

    articles = []
    cutoff   = utc_now() - timedelta(hours=HOURS_LOOKBACK)

    for sub_cfg in REDDIT_SUBREDDITS:
        sub_name = sub_cfg["name"]
        lean     = sub_cfg["lean"]
        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.hot(limit=REDDIT_MAX_POSTS):
                # Filter low-quality and old posts
                import datetime as dt_mod
                post_dt = datetime.fromtimestamp(
                    post.created_utc, tz=timezone.utc
                )
                # Use lower threshold for specialist subs
                specialist_subs = {"CredibleDefense", "OSINT", "nuclearweapons",
                                   "sanctions", "IntelligenceAnalysis", "GlobalPowers",
                                   "UkrainianConflict", "syriancivilwar", "Sudan"}
                min_score = 20 if sub_name in specialist_subs else REDDIT_MIN_SCORE
                if post.score < min_score:
                    continue
                if post_dt < cutoff:
                    continue
                if post.is_self and len(post.selftext or "") < 50:
                    continue  # Skip empty self-posts

                # Build a rich text field combining title + selftext
                body_text = ""
                if post.is_self and post.selftext:
                    body_text = post.selftext[:600]

                url = post.url if not post.is_self else f"https://reddit.com{post.permalink}"

                articles.append({
                    "title":     f"[r/{sub_name}] {post.title}",
                    "summary":   (body_text or post.title)[:400],
                    "url":       url,
                    "source":    f"Reddit/r/{sub_name}",
                    "lean":      lean,
                    "published": post_dt.isoformat(),
                    "text":      f"{post.title}. {body_text[:200]}",
                    "body":      body_text if body_text else None,
                    "entities":  "",
                    "score":     post.score,
                    "comments":  post.num_comments,
                    "platform":  "reddit",
                    "subreddit": sub_name,
                })

            time.sleep(0.5)  # Respect rate limits

        except Exception as e:
            print(f"  Reddit r/{sub_name} error: {e}")

    print(f"  Reddit: {len(articles)} posts from {len(REDDIT_SUBREDDITS)} subreddits")
    return articles


# ─────────────────────────────────────────────
# TELEGRAM — via Telethon (official MTProto API)
# ─────────────────────────────────────────────
#
# Setup (one-time):
#   1. Go to https://my.telegram.org/apps
#   2. Create an app — get API_ID and API_HASH
#   3. Add TELEGRAM_API_ID, TELEGRAM_API_HASH,
#      TELEGRAM_PHONE to Replit Secrets
#   4. First run will ask for SMS verification code
#      (saves session file, never asks again)
#
# Key channels for intelligence:
#   Intel channels, war reporters, OSINT accounts
#   that break conflict news before wire services

TELEGRAM_CHANNELS = [
    # ── Wire / breaking ───────────────────────────────────────────
    {"channel": "bbcbreaking",         "lean": "centre",             "label": "BBC Breaking"},
    {"channel": "AJEnglish",           "lean": "centre-left",        "label": "Al Jazeera EN"},
    {"channel": "AFPenglish",          "lean": "centre",             "label": "AFP"},
    {"channel": "reutersagency",       "lean": "centre",             "label": "Reuters"},

    # ── Ukraine / Russia conflict ──────────────────────────────────
    {"channel": "wartranslated",       "lean": "ukraine-focused",    "label": "War Translated"},
    {"channel": "UkraineNow",          "lean": "ukraine-state",      "label": "Ukraine Now"},
    {"channel": "rybar_en",            "lean": "russian-milblogger", "label": "Rybar (EN)"},
    {"channel": "intelslava",          "lean": "russian-osint",      "label": "Intel Slava Z"},
    {"channel": "DeepStateEN",         "lean": "ukraine-osint",      "label": "DeepState EN"},
    {"channel": "GeoConfirmed",        "lean": "osint",              "label": "GeoConfirmed"},
    {"channel": "aurora_intel",        "lean": "osint",              "label": "Aurora Intel"},

    # ── Iran / Middle East ─────────────────────────────────────────
    {"channel": "IranIntl_En",         "lean": "iran-opposition",    "label": "Iran International"},
    {"channel": "MEEupdate",           "lean": "centre-left",        "label": "Middle East Eye"},
    {"channel": "alaraby_en",          "lean": "centre",             "label": "Al-Araby English"},
    {"channel": "iran_war_monitor",    "lean": "analytical",         "label": "Iran War Monitor"},
    {"channel": "IranNewswire",        "lean": "iran-opposition",    "label": "Iran Newswire"},

    # ── Africa / Sudan ────────────────────────────────────────────
    {"channel": "sudanwarmonitor",     "lean": "conflict-data",      "label": "Sudan War Monitor"},
    {"channel": "HalfThePicture",      "lean": "analytical",         "label": "Half the Picture"},  # Sudan
    {"channel": "AfricaNewsAgency",    "lean": "pan-african",        "label": "Africa News"},

    # ── Investigations / OSINT ────────────────────────────────────
    {"channel": "bellingcat",          "lean": "investigative-osint","label": "Bellingcat"},
    {"channel": "occrp",               "lean": "investigative",      "label": "OCCRP"},
    {"channel": "isw_osint",           "lean": "nato-aligned",       "label": "ISW OSINT"},
    {"channel": "conflictmonitor",     "lean": "osint",              "label": "Conflict Monitor"},  # ACLED
    {"channel": "IntelligenceBrief",   "lean": "analytical",         "label": "Intelligence Brief"},

    # ── Sanctions / financial intelligence ────────────────────────
    {"channel": "sanctionsradar",      "lean": "analytical",         "label": "Sanctions Radar"},
    {"channel": "opensanctions",       "lean": "investigative",      "label": "OpenSanctions"},
]
BLUESKY_KEYWORDS = [
    # Conflict
    "ukraine war", "iran war", "hormuz blockade", "sudan RSF", "Gaza ceasefire",
    "Manipur violence", "Yemen strike",
    # Intelligence / investigations
    "OSINT", "sanctions evasion", "war crimes", "ICC indictment",
    "money laundering", "oligarch", "dark fleet", "shadow banking",
    # Narrative / disinfo
    "disinformation", "propaganda", "narrative shift", "information operation",
    "Doppelganger", "cognitive warfare",
    # Key actors
    "Zelensky", "Khamenei", "Vance Iran", "JD Vance Iran", "Araghchi",
    "Asim Munir", "CENTCOM", "IAEA Iran",
    # Financial
    "oil price", "Brent crude", "Iran sanctions", "Russia sanctions",
    "SWIFT exclusion", "frozen assets",
]

# Bluesky accounts to follow (independent journalists + OSINT)
BLUESKY_ACCOUNTS = [
    "bellingcat.bsky.social",
    "nahaltoosi.bsky.social",       # Politico national security
    "laraseligman.bsky.social",     # Politico defense
    "jonathanlanday.bsky.social",   # Reuters national security
    "karenmdevine.bsky.social",     # AP foreign
    "emptywheel.bsky.social",       # Marcy Wheeler — intel
    "travisj.bsky.social",          # ABC News investigative
    "nancyayoussef.bsky.social",    # WSJ national security
    "courtneykube.bsky.social",     # NBC News Pentagon
    "hanaagha.bsky.social",         # Afghan journalist
    "lindsey.bsky.social",          # Conflict reporter
]


# Max messages per channel per cycle
TELEGRAM_MAX_MESSAGES = 15
# Min message length to include
TELEGRAM_MIN_LENGTH   = 80

try:
    from telethon import TelegramClient
    from telethon.tl.functions.messages import GetHistoryRequest
    TELETHON_AVAILABLE = True
    print("Telethon available — Telegram module enabled")
except ImportError:
    TELETHON_AVAILABLE = False
    print("telethon not installed — Telegram disabled")
    print("  Install: pip install telethon")


def fetch_telegram():
    """
    Pull recent messages from public Telegram channels.
    Returns articles in the same format as fetch_rss().
    Requires TELEGRAM_API_ID, TELEGRAM_API_HASH in env.
    Session file is saved locally after first auth.
    """
    if not TELETHON_AVAILABLE:
        return []

    api_id   = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    phone    = os.environ.get("TELEGRAM_PHONE")

    if not api_id or not api_hash:
        print("  Telegram: TELEGRAM_API_ID / TELEGRAM_API_HASH not set — skipping")
        return []

    articles = []
    cutoff   = utc_now() - timedelta(hours=HOURS_LOOKBACK)

    # Use synchronous client to fit existing scraper pattern
    import asyncio

    async def _fetch():
        client = TelegramClient("parallax_session", int(api_id), api_hash)
        await client.start(phone=phone)

        for ch_cfg in TELEGRAM_CHANNELS:
            channel_name = ch_cfg["channel"]
            lean         = ch_cfg["lean"]
            label        = ch_cfg["label"]
            try:
                entity = await client.get_entity(channel_name)
                messages = await client.get_messages(
                    entity, limit=TELEGRAM_MAX_MESSAGES
                )
                count = 0
                for msg in messages:
                    if not msg.text or len(msg.text) < TELEGRAM_MIN_LENGTH:
                        continue
                    if not msg.date:
                        continue
                    msg_dt = msg.date.replace(tzinfo=timezone.utc)
                    if msg_dt < cutoff:
                        continue

                    # Build URL to the specific message
                    url = f"https://t.me/{channel_name}/{msg.id}"

                    # First line often acts as headline
                    lines = msg.text.strip().split("\n")
                    headline = lines[0][:120] if lines else msg.text[:120]
                    body     = msg.text[:600]

                    articles.append({
                        "title":     f"[Telegram/{label}] {headline}",
                        "summary":   body[:400],
                        "url":       url,
                        "source":    f"Telegram/{label}",
                        "lean":      lean,
                        "published": msg_dt.isoformat(),
                        "text":      body[:300],
                        "body":      body,
                        "entities":  extract_entities(body),
                        "platform":  "telegram",
                        "channel":   channel_name,
                    })
                    count += 1

                print(f"    @{channel_name}: {count} messages")
                await asyncio.sleep(0.5)

            except Exception as e:
                print(f"    Telegram @{channel_name} error: {e}")

        await client.disconnect()
        return articles

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_fetch())
        loop.close()
        print(f"  Telegram: {len(result)} messages from {len(TELEGRAM_CHANNELS)} channels")
        return result
    except Exception as e:
        print(f"  Telegram fetch error: {e}")
        return []


# ─────────────────────────────────────────────
# BLUESKY — via atproto (open firehose, no key)
# ─────────────────────────────────────────────
#
# No API key needed — Bluesky is an open protocol.
# We search for posts by keyword rather than using
# the raw firehose (which is too high-volume).
# Focus: breaking news, journalist accounts.
#
# Optional: add BLUESKY_HANDLE + BLUESKY_PASSWORD
# to Replit Secrets for higher rate limits.

BLUESKY_SEARCH_TERMS = [
    "breaking news", "conflict", "war", "Ukraine",
    "Gaza", "Sudan", "Iran", "sanctions",
    "coup", "ceasefire", "airstrike", "protest",
]

BLUESKY_MAX_RESULTS  = 20
BLUESKY_MIN_LIKES    = 3   # Filter noise

try:
    from atproto import Client as BskyClient, client_utils
    ATPROTO_AVAILABLE = True
    print("atproto available — Bluesky module enabled")
except ImportError:
    ATPROTO_AVAILABLE = False
    print("atproto not installed — Bluesky disabled")
    print("  Install: pip install atproto")


def fetch_bluesky():
    """
    Fetch from Bluesky using keyword search AND account timelines.
    Tracks independent journalists and OSINT accounts directly.
    No credentials required for public search/timelines.
    """
    if not ATPROTO_AVAILABLE:
        return []

    handle   = os.environ.get("BLUESKY_HANDLE")
    password = os.environ.get("BLUESKY_PASSWORD")
    articles = []

    try:
        client = BskyClient()
        if handle and password:
            try:
                client.login(handle, password)
            except Exception as e:
                print(f"  Bluesky login error: {e}")
        # Anonymous access works for public data

        # ── 1. Keyword searches ───────────────────────────────────
        bsky_keywords = BLUESKY_KEYWORDS[:12]  # top 12 keywords

        seen_uris = set()
        for keyword in bsky_keywords[:8]:  # limit to 8 searches to avoid rate limits
            try:
                resp = client.app.bsky.feed.search_posts({"q": keyword, "limit": 15, "sort": "latest"})
                posts = resp.posts if hasattr(resp, 'posts') else []
                for post in posts:
                    text = getattr(getattr(post, 'record', None), 'text', None) or ''
                    if len(text) < 30:
                        continue
                    # Filter for signal quality
                    has_link = 'http' in text or hasattr(post, 'embed')
                    like_count = getattr(post, 'likeCount', 0) or 0
                    repost_count = getattr(post, 'repostCount', 0) or 0
                    # Minimum engagement or has a link
                    if like_count < 3 and repost_count < 2 and not has_link:
                        continue
                    uri = getattr(post, 'uri', '')
                    if uri in seen_uris:
                        continue
                    seen_uris.add(uri)
                    author = getattr(post, 'author', None)
                    handle_str = getattr(author, 'handle', 'unknown') if author else 'unknown'
                    display_name = getattr(author, 'displayName', handle_str) if author else handle_str
                    indexed_at = getattr(post, 'indexedAt', utc_now().isoformat())
                    articles.append({
                        "title":     text[:140],
                        "summary":   text,
                        "source":    f"Bluesky/{display_name}",
                        "url":       f"https://bsky.app/profile/{handle_str}",
                        "published": indexed_at,
                        "lean":      "social-bluesky",
                        "platform":  "bluesky",
                        "text":      text,
                        "body":      None,
                        "entities":  "",
                        "engagement": like_count + repost_count * 2,
                    })
                time.sleep(0.3)
            except Exception as e:
                print(f"  Bluesky search '{keyword}': {e}")

        # ── 2. Account timelines (independent journalists) ────────
        try:
            bsky_accounts = BLUESKY_ACCOUNTS
        except NameError:
            bsky_accounts = [
                "bellingcat.bsky.social",
                "nahaltoosi.bsky.social",
                "emptywheel.bsky.social",
            ]

        for account in bsky_accounts[:8]:  # limit accounts checked per cycle
            try:
                resp = client.app.bsky.feed.get_author_feed({"actor": account, "limit": 8})
                feed = resp.feed if hasattr(resp, 'feed') else []
                for item in feed:
                    post = getattr(item, 'post', None)
                    if not post:
                        continue
                    text = getattr(getattr(post, 'record', None), 'text', None) or ''
                    if len(text) < 40:
                        continue
                    uri = getattr(post, 'uri', '')
                    if uri in seen_uris:
                        continue
                    seen_uris.add(uri)
                    like_count    = getattr(post, 'likeCount', 0) or 0
                    repost_count  = getattr(post, 'repostCount', 0) or 0
                    indexed_at    = getattr(post, 'indexedAt', utc_now().isoformat())
                    articles.append({
                        "title":     text[:140],
                        "summary":   text,
                        "source":    f"Bluesky/{account.split('.')[0]}",
                        "url":       f"https://bsky.app/profile/{account}",
                        "published": indexed_at,
                        "lean":      "independent-journalist",
                        "platform":  "bluesky",
                        "text":      text,
                        "body":      None,
                        "entities":  "",
                        "engagement": like_count + repost_count * 2,
                    })
                time.sleep(0.3)
            except Exception as e:
                print(f"  Bluesky account {account}: {e}")

        # Sort by engagement + recency
        articles.sort(key=lambda a: (a.get('engagement', 0), a.get('published', '')), reverse=True)
        print(f"  Bluesky: {len(articles)} posts ({len(bsky_keywords[:8])} keywords + {len(bsky_accounts[:8])} accounts)")
        return articles[:60]  # cap total

    except Exception as e:
        print(f"  Bluesky error: {e}")
        return []



def archive_url_wayback(url):
    """
    Submit a URL to the Internet Archive Wayback Machine for preservation.
    Called for high-confidence stories so sources can't be deleted later.
    Returns the archive URL if successful.
    """
    if not url or not url.startswith("http"):
        return None
    try:
        archive_endpoint = f"https://web.archive.org/save/{url}"
        req = Request(archive_endpoint, headers={"User-Agent": "Parallax/1.0"})
        with urlopen(req, timeout=15) as r:
            # Wayback returns Content-Location with the archive URL
            location = r.headers.get("Content-Location","")
            if location:
                return f"https://web.archive.org{location}"
        return None
    except Exception:
        return None  # Non-fatal — archiving is best-effort

def fetch_gdelt():
    """
    GDELT Article List with conflict-focused tone filtering and
    full metadata extraction. Pulls articles with negative tone
    (conflict/crisis) AND most-shared (viral signals).
    Also queries GDELT Events API for conflict event data.
    """
    items = []

    # ── Article list: negative tone (crisis/conflict) ─────────────
    params_neg = {
        "query": "sourcelang:english",
        "mode": "ArtList",
        "maxrecords": "25",
        "timespan": "24h",
        "format": "json",
        "sort": "ToneAsc"      # Most negative tone first
    }
    data = fetch_url(GDELT_API + "?" + urlencode(params_neg))
    if data:
        try:
            for a in json.loads(data).get("articles", []):
                t = a.get("title","").strip()
                if not t or len(t) < 10: continue
                # Extract GDELT metadata
                tone     = a.get("tone", 0)
                seendate = a.get("seendate","")
                lang     = a.get("language","")
                country  = a.get("sourcecountry","")
                items.append({
                    "title":     t,
                    "summary":   a.get("socialimage",""),
                    "url":       a.get("url",""),
                    "source":    a.get("domain","GDELT"),
                    "lean":      "data",
                    "published": utc_now().isoformat(),
                    "text":      t,
                    "body":      None,
                    "entities":  "",
                    "platform":  "gdelt",
                    "gdelt_tone":    tone,
                    "gdelt_country": country,
                    "geo_lat":   "",
                    "geo_lon":   "",
                })
        except Exception as e:
            print(f"  GDELT articles error: {e}")

    # ── Article list: most shared (social virality signal) ────────
    params_social = {
        "query": "sourcelang:english",
        "mode": "ArtList",
        "maxrecords": "15",
        "timespan": "6h",       # last 6 hours for viral signals
        "format": "json",
        "sort": "SocialCountSum" # Most shared
    }
    data2 = fetch_url(GDELT_API + "?" + urlencode(params_social))
    if data2:
        try:
            for a in json.loads(data2).get("articles", []):
                t = a.get("title","").strip()
                if not t or len(t) < 10: continue
                social_score = (a.get("socialshares",0) or 0) + (a.get("socialimage",0) or 0)
                items.append({
                    "title":     t,
                    "summary":   "",
                    "url":       a.get("url",""),
                    "source":    a.get("domain","GDELT-social"),
                    "lean":      "viral-signal",
                    "published": utc_now().isoformat(),
                    "text":      t,
                    "body":      None,
                    "entities":  "",
                    "platform":  "gdelt",
                    "gdelt_social_score": social_score,
                })
        except Exception as e:
            print(f"  GDELT social error: {e}")

    return items

# ─────────────────────────────────────────────
# CLUSTERING
# ─────────────────────────────────────────────
STOPWORDS = {"the","a","an","in","on","at","to","of","for","and","or","is","was",
             "are","were","has","have","had","with","by","from","as","that","this",
             "it","its","he","she","they","said","says","will","would","could","not",
             "but","new","after","before","over","than","then","us","uk","also"}

def words(text):
    return set(w for w in re.findall(r'[a-z]{4,}', text.lower()) if w not in STOPWORDS)

def sim(a, b):
    """
    Multi-signal similarity for clustering:
    1. Word Jaccard on title+body text (base)
    2. Named entity overlap bonus — "Gaza" and "Hamas" in both = strong signal
    3. Author identity bonus — same journalist covering same story
    4. Category/tag overlap — feeds that tag stories similarly

    This fixes the core problem: "Gaza ceasefire" and "Hamas truce negotiations"
    share zero word tokens but share entities (Gaza, Hamas, ceasefire concept).
    """
    # Base: word Jaccard
    sa, sb = words(a["text"]), words(b["text"])
    base = (len(sa & sb) / len(sa | sb)) if (sa and sb) else 0.0

    # Entity overlap bonus — extract capitalised proper nouns from titles
    def title_entities(art):
        t = art.get("title","")
        # Capitalised words 3+ chars that aren't stopwords
        return {w for w in re.findall(r"[A-Z][a-z]{2,}", t)
                if w.lower() not in STOPWORDS}

    ea, eb = title_entities(a), title_entities(b)
    entity_bonus = 0.0
    if ea and eb:
        shared = len(ea & eb)
        if shared >= 2:
            entity_bonus = 0.15   # 2+ shared named entities = strong signal
        elif shared == 1:
            entity_bonus = 0.07   # 1 shared named entity = moderate signal

    # Bigram overlap on title — catches "ceasefire talks" / "ceasefire negotiations"
    def title_bigrams(art):
        ws = [w for w in re.findall(r"[a-z]{3,}", art.get("title","").lower())
              if w not in STOPWORDS]
        return {(ws[i], ws[i+1]) for i in range(len(ws)-1)}

    ba, bb = title_bigrams(a), title_bigrams(b)
    bigram_bonus = 0.0
    if ba and bb and (ba & bb):
        bigram_bonus = 0.08

    # Source diversity — different sources on same story is MORE valuable
    # No same-source penalty here; handled by cluster quality filter

    total = base + entity_bonus + bigram_bonus
    return min(total, 1.0)

def cluster(articles, threshold=0.12):
    clusters, used = [], set()
    for i, art in enumerate(articles):
        if i in used: continue
        grp = [art]; used.add(i)
        for j, other in enumerate(articles):
            if j not in used and sim(art, other) >= threshold:
                grp.append(other); used.add(j)
        clusters.append(grp)
    return sorted(clusters, key=len, reverse=True)

# ─────────────────────────────────────────────
# CLAUDE
# ─────────────────────────────────────────────
def call_claude(prompt, max_tokens=900):
    if not ANTHROPIC_API_KEY: return None
    payload = json.dumps({
        "model": MODEL, "max_tokens": max_tokens,
        "messages": [{"role":"user","content":prompt}]
    }).encode()
    req = Request("https://api.anthropic.com/v1/messages", data=payload,
        headers={"Content-Type":"application/json","x-api-key":ANTHROPIC_API_KEY,
                 "anthropic-version":"2023-06-01"}, method="POST")
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read())["content"][0]["text"]
    except Exception as e:
        print(f"  Claude error: {e}"); return None


# ─────────────────────────────────────────────
# SIGNAL VELOCITY & NARRATIVE DRIFT
# ─────────────────────────────────────────────

VELOCITY_FILE = "velocity_history.json"
NARRATIVE_FILE = "narrative_history.json"
STORY_HISTORY_FILE       = "story_history.json"

def load_json_file(path, default=None):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}

def save_json_file(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"  Save error {path}: {e}")


def score_signal_velocity(cluster, story_id_str):
    """
    Score 0-100 measuring how credibly a story has propagated.

    A real breaking event follows:
      Telegram/social (first) → wire services → analysis outlets

    A disinformation campaign follows:
      Social media saturation → wire services absent or debunking

    Scoring:
      +30  Wire source present (moved beyond social)
      +20  Wire source present AND social source present (natural propagation)
      +15  2+ independent tiers represented
      +15  Story appeared in previous scrape cycle (persistent, not fleeting)
      -20  Social-only cluster (no tier 1/2 sources at all)
      -10  >80% of articles are provisional (<2 hours old)
      +10  Non-Western and Western sources both present
    """
    score = 50  # Baseline

    tiers = [get_source_tier(a["source"]) for a in cluster]
    has_wire    = any(t <= 2 for t in tiers)
    has_social  = any(t == 5 for t in tiers)
    tier_set    = set(tiers)
    prov_ratio  = cluster_provisional_ratio(cluster)

    if has_wire:   score += 30
    if has_wire and has_social: score += 20   # Natural propagation pattern
    if len(tier_set) >= 2: score += 15
    if not has_wire: score -= 20              # Social-only = low credibility
    if prov_ratio > 0.8: score -= 10          # Almost all brand-new = breaking caution

    # Cross-perspective bonus
    sources = {a["source"] for a in cluster}
    western_present    = any(s in ("Reuters","AP","BBC","DW") for s in sources)
    nonwestern_present = any(
        any(k in s for k in ("Al Jazeera","SCMP","Times of India","Africa","TASS","Global Times"))
        for s in sources
    )
    if western_present and nonwestern_present: score += 10

    # Persistence bonus — did this story exist last cycle?
    velocity_history = load_json_file(VELOCITY_FILE, {})
    if story_id_str in velocity_history:
        score += 15

    return max(0, min(100, score))


def detect_contradictions(cluster):
    """
    Identify when sources in a cluster directly contradict each other.
    Returns a list of contradiction pairs for the Claude prompt.
    Simple heuristic: if high-tier sources and state-media sources
    are both present, flag for explicit treatment.
    """
    wire_sources    = [a for a in cluster if get_source_tier(a["source"]) <= 2]
    state_sources   = [a for a in cluster if get_source_tier(a["source"]) == 4]
    social_sources  = [a for a in cluster if get_source_tier(a["source"]) == 5]

    flags = []
    if wire_sources and state_sources:
        wire_names  = [a["source"] for a in wire_sources[:2]]
        state_names = [a["source"] for a in state_sources[:2]]
        flags.append(
            f"DIRECT CONFLICT: {', '.join(wire_names)} (independent) "
            f"vs {', '.join(state_names)} (state-aligned) — "
            f"treat these as competing narratives, not corroboration"
        )

    if social_sources and not wire_sources:
        social_names = list({a["source"] for a in social_sources[:3]})
        flags.append(
            f"SOCIAL-ONLY: {', '.join(social_names)} — "
            f"no wire service corroboration yet — mark as unverified signal"
        )

    prov_ratio = cluster_provisional_ratio(cluster)
    if prov_ratio > 0.6:
        flags.append(
            f"PROVISIONAL: {int(prov_ratio*100)}% of sources published <2 hours ago — "
            f"breaking reports frequently require correction — confidence ceiling: low"
        )

    return flags


def save_velocity_record(stories):
    """
    After each scrape, save story IDs and their source tier composition
    so next cycle can detect persistence.
    """
    history = load_json_file(VELOCITY_FILE, {})
    now = utc_now().isoformat()
    for story in stories:
        sid = story.get("id","")
        if not sid: continue
        if sid not in history:
            history[sid] = {"first_seen": now, "cycles": 1, "velocity_scores": []}
        else:
            history[sid]["cycles"] = history[sid].get("cycles",1) + 1
        history[sid]["last_seen"] = now
        history[sid]["velocity_scores"].append(story.get("signal_score", 50))
        # Keep only last 20 cycles
        history[sid]["velocity_scores"] = history[sid]["velocity_scores"][-20:]
    # Prune entries older than 7 days
    cutoff = (utc_now() - timedelta(days=7)).isoformat()
    history = {k:v for k,v in history.items() if v.get("last_seen","") >= cutoff}
    save_json_file(VELOCITY_FILE, history)


def save_narrative_snapshot(stories):
    """
    Save headline, confidence, summary hash, and source set each cycle.
    Builds the drift-detection and version history datasets.
    """
    snapshots = load_json_file(NARRATIVE_FILE, {})
    history   = load_json_file(STORY_HISTORY_FILE, {})
    now       = utc_now().isoformat()

    for story in stories:
        sid = story.get("id","")
        if not sid: continue

        snapshot = {
            "time":         now,
            "headline":     story.get("headline",""),
            "confidence":   story.get("confidence","low"),
            "score":        story.get("signal_score", 50),
            "summary_hash": hashlib.md5(story.get("summary","").encode()).hexdigest()[:8],
            "sources":      story.get("sources", [])[:8],
            "what_is_known": story.get("what_is_known", [])[:3],
            "what_is_disputed": story.get("what_is_disputed",""),
            "region":       story.get("region",""),
            "category":     story.get("category",""),
        }

        # ── Narrative history (lightweight, for drift detection) ──
        if sid not in snapshots:
            snapshots[sid] = {"snapshots": []}
        snaps = snapshots[sid]["snapshots"]
        # Only save if something changed (headline or confidence or sources)
        if not snaps or (
            snaps[-1]["headline"]   != snapshot["headline"] or
            snaps[-1]["confidence"] != snapshot["confidence"] or
            set(snaps[-1].get("sources",[])) != set(snapshot["sources"])
        ):
            snaps.append(snapshot)
        snapshots[sid]["snapshots"] = snaps[-48:]  # keep 48 cycles max (~24h)

        # ── Full story version history (for Cascade Previous Versions) ──
        if sid not in history:
            history[sid] = {"versions": []}
        versions = history[sid]["versions"]
        # Save a full version snapshot when meaningful content changes
        prev_headline = versions[-1]["headline"] if versions else ""
        prev_hash     = versions[-1]["summary_hash"] if versions else ""
        if prev_headline != snapshot["headline"] or prev_hash != snapshot["summary_hash"]:
            versions.append({
                **snapshot,
                "summary":     story.get("summary","")[:800],
                "version_num": len(versions) + 1,
            })
        history[sid]["versions"] = versions[-20:]  # keep 20 versions max

    # Prune stale entries (not seen in 3 days)
    cutoff = (utc_now() - timedelta(days=3)).isoformat()
    snapshots = {k: v for k,v in snapshots.items()
                 if v["snapshots"] and v["snapshots"][-1]["time"] >= cutoff}
    history   = {k: v for k,v in history.items()
                 if v["versions"] and v["versions"][-1]["time"] >= cutoff}

    save_json_file(NARRATIVE_FILE, snapshots)
    save_json_file(STORY_HISTORY_FILE, history)


def detect_narrative_drift(story_id_str):
    """
    Multi-signal narrative drift detection:
    1. Confidence trajectory
    2. Headline framing changes
    3. Source expansion/contraction + source tier shifts
    4. Summary hash divergence (covert reframing)
    5. What-is-known / what-is-disputed framing shifts
    6. Cross-version keyword drift (claims that appear then disappear)
    Returns a human-readable drift note and structured drift events list.
    """
    snapshots = load_json_file(NARRATIVE_FILE, {})
    entry     = snapshots.get(story_id_str)
    if not entry or len(entry.get("snapshots",[])) < 2:
        return "", []

    snaps  = entry["snapshots"]
    first  = snaps[0]
    latest = snaps[-1]
    notes  = []
    events = []

    conf_map = {"low": 1, "medium": 2, "high": 3}
    fc = conf_map.get(first.get("confidence","low"), 1)
    lc = conf_map.get(latest.get("confidence","low"), 1)

    # 1. Confidence trajectory
    if lc > fc:
        notes.append(f"confidence rose {first['confidence']}→{latest['confidence']} over {len(snaps)} cycles")
        events.append({"type":"confidence_up","from":first["confidence"],"to":latest["confidence"],
                       "time":latest["time"],"detail":"Corroboration improving — new independent sources added"})
    elif lc < fc:
        notes.append(f"confidence dropped {first['confidence']}→{latest['confidence']} — story contested or corrected")
        events.append({"type":"confidence_down","from":first["confidence"],"to":latest["confidence"],
                       "time":latest["time"],"detail":"Story being challenged or corrected by new evidence"})

    # 2. Headline framing changes
    headlines = [s["headline"] for s in snaps]
    unique_hls = list(dict.fromkeys(headlines))
    if len(unique_hls) >= 2:
        notes.append(f"headline framing changed {len(unique_hls)} times")
        for i in range(1, min(len(unique_hls), 5)):
            events.append({"type":"headline_change","from":unique_hls[i-1][:100],
                           "to":unique_hls[i][:100],"time":snaps[i]["time"],
                           "detail":"Narrative framing shift detected in headline"})

    # 3. Source expansion/contraction and tier analysis
    first_srcs  = set(first.get("sources",[]))
    latest_srcs = set(latest.get("sources",[]))
    added   = latest_srcs - first_srcs
    dropped = first_srcs - latest_srcs

    # Source tier shift — check if story moved from state/social sources to wire sources
    wire_sources    = {"reuters","ap","afp","bbc","guardian","nyt","wsj","bloomberg","ft"}
    state_sources   = {"tass","xinhua","irna","rt","sputnik","cgtn","presstviran"}
    first_has_wire  = any(s.lower() in wire_sources for s in first_srcs)
    latest_has_wire = any(s.lower() in wire_sources for s in latest_srcs)
    first_has_state = any(s.lower() in state_sources for s in first_srcs)
    latest_has_state = any(s.lower() in state_sources for s in latest_srcs)

    if not first_has_wire and latest_has_wire:
        notes.append("wire sources entered — story escalating in credibility")
        events.append({"type":"tier_upgrade","time":latest["time"],
                       "detail":"Wire services (Reuters/AP/BBC etc) now covering — story gaining independent corroboration"})
    elif first_has_wire and not latest_has_wire:
        notes.append("wire sources dropped out — story may be contested or cooling")
        events.append({"type":"tier_downgrade","time":latest["time"],
                       "detail":"Wire services stopped covering — check for corrections or story cooling"})

    if not first_has_state and latest_has_state:
        events.append({"type":"state_media_entered","time":latest["time"],
                       "detail":"State media now covering — potential narrative management or counter-framing"})
    elif first_has_state and not latest_has_state:
        events.append({"type":"state_media_dropped","time":latest["time"],
                       "detail":"State media stopped covering — may indicate story is no longer useful for that government"})

    if added:
        notes.append(f"new sources: {', '.join(list(added)[:3])}")
        events.append({"type":"sources_added","sources":list(added)[:6],"time":latest["time"],
                       "detail":f"{len(added)} new source(s) now covering"})
    if dropped:
        events.append({"type":"sources_dropped","sources":list(dropped)[:6],"time":latest["time"],
                       "detail":f"{len(dropped)} source(s) stopped covering"})

    # 4. Summary hash divergence (covert reframing)
    unique_hashes = list(dict.fromkeys(s["summary_hash"] for s in snaps))
    if len(unique_hashes) >= 3 and len(unique_hls) <= 1:
        notes.append(f"covert reframing: content changed {len(unique_hashes)} times without headline change")
        events.append({"type":"covert_reframe","count":len(unique_hashes),"time":latest["time"],
                       "detail":"Summary content changed significantly while headline stayed the same — potential quiet correction"})

    # 5. What-is-known framing shifts
    first_known  = set(str(x).lower()[:50] for x in first.get("what_is_known",[]))
    latest_known = set(str(x).lower()[:50] for x in latest.get("what_is_known",[]))
    facts_added   = len(latest_known - first_known)
    facts_removed = len(first_known - latest_known)
    if facts_removed >= 1:
        notes.append(f"{facts_removed} previously stated fact(s) removed — possible correction")
        events.append({"type":"facts_removed","count":facts_removed,"time":latest["time"],
                       "detail":f"{facts_removed} claim(s) that appeared in earlier versions are no longer stated — check for corrections"})
    if facts_added >= 2:
        events.append({"type":"facts_added","count":facts_added,"time":latest["time"],
                       "detail":f"{facts_added} new confirmed facts added — story developing"})

    # 6. Disputed section expansion (story becoming more contested)
    first_disputed  = len(first.get("what_is_disputed",""))
    latest_disputed = len(latest.get("what_is_disputed",""))
    if latest_disputed > first_disputed * 1.5 and latest_disputed > 100:
        notes.append("contested claims section expanding — story becoming more disputed")
        events.append({"type":"dispute_expansion","time":latest["time"],
                       "detail":"What-is-disputed section has grown significantly — more claims being challenged"})

    # Velocity analysis: how fast are snapshots accumulating?
    if len(snaps) >= 6:
        recent = snaps[-3:]
        early  = snaps[:3]
        recent_changes = sum(1 for i in range(1,len(recent)) if recent[i]["summary_hash"] != recent[i-1]["summary_hash"])
        early_changes  = sum(1 for i in range(1,len(early))  if early[i]["summary_hash"]  != early[i-1]["summary_hash"])
        if recent_changes > early_changes:
            events.append({"type":"velocity_increasing","time":latest["time"],
                           "detail":"Story changing faster recently than at start — active development or controversy"})
        elif recent_changes < early_changes and early_changes >= 2:
            events.append({"type":"velocity_decreasing","time":latest["time"],
                           "detail":"Story stabilising — fewer changes in recent cycles"})

    drift_note = "; ".join(notes) if notes else ""
    return drift_note, events


def check_absence_detection(all_articles):
    """
    Flag if ACLED conflict data is present but no wire service is covering it.
    Returns list of absence alerts.
    """
    acled_articles = [a for a in all_articles if "ACLED" in a.get("source","")]
    if not acled_articles:
        return []

    wire_titles = " ".join(
        a["title"].lower() for a in all_articles
        if get_source_tier(a["source"]) <= 2
    )

    alerts = []
    for acled_art in acled_articles[:10]:
        # Extract key location words from ACLED title
        title_words = set(acled_art["title"].lower().split())
        location_words = {w for w in title_words if len(w) > 4}
        overlap = sum(1 for w in location_words if w in wire_titles)
        if overlap < 2:  # ACLED event not well-covered by wire services
            alerts.append({
                "type": "absence",
                "headline": f"Potential underreported conflict: {acled_art['title'][:80]}",
                "note": "ACLED data shows conflict activity with minimal wire service coverage",
                "url": acled_art.get("url",""),
            })

    return alerts[:3]  # Max 3 absence alerts per cycle


def extract_quotes(text):
    """
    Extract direct quotes from article text.
    Returns list of {"quote": str, "attribution": str} dicts.
    """
    if not text: return []
    quotes = []
    # Pattern: "quote text" followed by attribution verb + name
    pattern = r'"([^"]{20,200})"[,\s]+(?:said|says|told|according to|stated|confirmed|denied|claimed|warned|announced)\s+([A-Z][^,.]{3,40})'
    for m in re.finditer(pattern, text):
        quotes.append({"quote": m.group(1).strip(), "attribution": m.group(2).strip()})
    # Also capture attributed quotes in reverse order: Name said "..."
    pattern2 = r'([A-Z][^,.]{3,30})\s+(?:said|says|told|confirmed|stated|warned|announced)[,\s]+"([^"]{20,200})"'
    for m in re.finditer(pattern2, text):
        quotes.append({"quote": m.group(2).strip(), "attribution": m.group(1).strip()})
    return quotes[:6]  # max 6 quotes per article

def extract_numbers(text):
    """
    Extract significant numbers and statistics from article text.
    These are often the most factually important elements.
    """
    if not text: return []
    numbers = []
    patterns = [
        # Dollar/currency amounts
        (r'\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|trillion|bn|mn))?', "financial"),
        (r'[\d,]+(?:\.\d+)?\s*(?:million|billion|trillion)\s+(?:dollars|euros|pounds|yuan)', "financial"),
        # Percentages
        (r'[\d.]+%(?:\s+(?:rise|fall|increase|decrease|growth|drop|up|down))?', "percentage"),
        # Casualties/counts
        (r'(?:killed|dead|died|wounded|injured|displaced|arrested|detained)[^\d]*(\d+(?:,\d+)*)', "casualty"),
        (r'(\d+(?:,\d+)*)\s+(?:people|civilians|soldiers|troops|protesters)\s+(?:killed|dead|wounded)', "casualty"),
        # Distances / areas
        (r'\d+(?:\.\d+)?\s*(?:km|kilometers|miles|km²|square\s+km)', "geographic"),
        # Time/duration
        (r'\d+\s*(?:days|weeks|months|years)\s+(?:ago|since|after|before)', "temporal"),
    ]
    for pattern, category in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            numbers.append({"value": match.group(0).strip(), "category": category})
    return numbers[:10]

def detect_article_type(title, body):
    """
    Classify article as breaking/analysis/opinion/primary-doc/correction.
    Affects how Claude weights it.
    """
    title_lower = (title or "").lower()
    body_lower  = (body  or "")[:200].lower()
    combined    = title_lower + " " + body_lower

    if any(w in combined for w in ["breaking:", "urgent:", "update:", "alert:", "flash:"]):
        return "breaking"
    if any(w in combined for w in ["report:", "reports:", "statement:", "announces", "confirmed"]):
        return "statement"
    if any(w in combined for w in ["analysis:", "explainer:", "what to know", "why it matters"]):
        return "analysis"
    if any(w in combined for w in ["opinion:", "op-ed:", "editorial:", "comment:", "view:"]):
        return "opinion"
    if any(w in combined for w in ["correction:", "editor's note:", "we reported incorrectly"]):
        return "correction"
    if any(w in combined for w in ["documents show", "according to documents", "files reveal", "leaked"]):
        return "primary-doc"
    return "news"

def enrich_articles(articles, max_per_cluster=6):
    """
    Fetch full article bodies for a cluster.
    Now extracts: full body, entities, direct quotes, key statistics,
    financial figures, article type, author byline, and related links.
    max_per_cluster raised from 5 to 6 for better coverage.
    """
    import concurrent.futures

    # Always fetch for primary document sources regardless of position
    primary_first = sorted(articles, key=lambda a: (
        0 if get_source_tier(a.get("source","")) == 0 else
        1 if get_source_tier(a.get("source","")) <= 2 else 2
    ))
    to_fetch = primary_first[:max_per_cluster]

    def fetch_one(article):
        if article.get("body") and len(article["body"]) > 200:
            # Already have good body — still extract structured data
            body = article["body"]
            article["quotes"]   = extract_quotes(body)
            article["numbers"]  = extract_numbers(body)
            article["art_type"] = detect_article_type(article.get("title",""), body)
            if not article.get("entities"):
                article["entities"] = extract_entities(body)
            return article

        result = fetch_article_body(article.get("url",""))
        if result and len(result["text"]) > 150:
            body = result["text"]
            article["body"]       = body
            article["entities"]   = extract_entities(body)
            article["quotes"]     = extract_quotes(body)
            article["numbers"]    = extract_numbers(body)
            article["art_type"]   = detect_article_type(article.get("title",""), body)
            article["word_count"] = result.get("word_count", 0)
            article["truncated"]  = result.get("truncated", False)
            if result["authors"] and not article.get("author"):
                article["author"] = ", ".join(result["authors"][:2])
        else:
            # Fall back to RSS content
            fallback = article.get("summary","")
            article["body"]      = fallback
            article["entities"]  = extract_entities(fallback) if fallback else ""
            article["quotes"]    = extract_quotes(fallback)
            article["numbers"]   = extract_numbers(fallback)
            article["art_type"]  = detect_article_type(article.get("title",""), fallback)
        return article

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futures = [ex.submit(fetch_one, a) for a in to_fetch]
        enriched = [f.result() for f in concurrent.futures.as_completed(futures)]

    enriched_map = {a["url"]: a for a in enriched}
    result = [enriched_map.get(a["url"], a) for a in to_fetch]
    result += articles[max_per_cluster:]
    return result


def find_cross_citations(cluster_articles):
    """
    Detect when articles in a cluster cite each other or share a common
    primary document source. This is a strong corroboration signal:
    - Article A cites Article B → B's URL appears in A's body text
    - Both articles link to the same primary document (court filing, report)
    Returns a list of citation relationships.
    """
    citations = []
    urls = {a.get("url","").split("?")[0]: a["source"] for a in cluster_articles if a.get("url")}

    for a in cluster_articles:
        body = a.get("body","") or ""
        for url, source in urls.items():
            if url and url in body and url != a.get("url",""):
                citations.append({
                    "citing": a["source"],
                    "cited":  source,
                    "note":   f"{a['source']} cites {source}"
                })

        # Also detect links to primary document domains
        primary_domains = [
            "iaea.org", "icc-cpi.int", "ohchr.org", "treasury.gov",
            "un.org", "acleddata.com", "icij.org", "occrp.org",
            "pacer.uscourts.gov", "sec.gov", "companieshouse.gov.uk"
        ]
        for domain in primary_domains:
            if domain in body:
                citations.append({
                    "citing": a["source"],
                    "cited":  f"primary:{domain}",
                    "note":   f"{a['source']} links to primary document at {domain}"
                })

    return citations[:6]  # max 6 citation relationships

def generate_story(cluster_articles):
    sources = list({a["source"] for a in cluster_articles})

    # ── Enrich articles with full body text before passing to Claude ──
    cluster_articles = enrich_articles(cluster_articles, max_per_cluster=6)

    # Format articles — now includes full body, entities, and source lean
    def fmt_article(a):
        """
        Format article for Claude prompt — now includes:
        - Article type (breaking/statement/analysis/opinion/correction/primary-doc)
        - Author byline
        - Direct quotes extracted from body text
        - Key statistics and numbers
        - Financial signals (dollar amounts, percentages)
        - Geographic coordinates if available
        - Categories/tags
        """
        lean_label = f" [{a.get('lean','unknown')} perspective]" if a.get('lean') else ""
        art_type   = a.get("art_type", "news")
        author     = a.get("author","")
        body       = (a.get("body") or a.get("summary","")).strip()
        url        = a.get("url","")

        out  = f'[{a["source"]}{lean_label}] [{art_type.upper()}]\n'
        if author:
            out += f'  Byline: {author}\n'
        out += f'  Headline: {a["title"]}\n'

        if body:
            body_label = "Full article text" if len(body) > 300 else "Summary"
            out += f'  {body_label}: {body[:1000]}\n'

        # Direct quotes — most valuable for attribution accuracy
        quotes = a.get("quotes", [])
        if quotes:
            out += f'  Direct quotes:\n'
            for q in quotes[:3]:
                out += f'    — "{q["quote"]}" — {q["attribution"]}\n'

        # Key numbers — statistics, casualties, financial figures
        numbers = a.get("numbers", [])
        if numbers:
            num_str = " | ".join(n["value"] for n in numbers[:5])
            out += f'  Key figures: {num_str}\n'

        # Financial signals from RSS
        fin_sigs = a.get("financial_signals", [])
        if fin_sigs:
            out += f'  Financial signals: {", ".join(fin_sigs[:4])}\n'

        if a.get("entities"):
            out += f'  Named entities: {a["entities"]}\n'

        if a.get("categories"):
            out += f'  Tags: {", ".join(a["categories"][:4])}\n'

        if a.get("geo_lat") and a.get("geo_lon"):
            out += f'  Coordinates: {a["geo_lat"]},{a["geo_lon"]}\n'

        if a.get("gdelt_tone") is not None:
            out += f'  GDELT tone score: {a["gdelt_tone"]:.1f} (negative=crisis)\n'

        if url:
            out += f'  Source URL: {url}\n'

        return out

    article_text = "\n".join(fmt_article(a) for a in cluster_articles[:8])
    lean_labels  = list({a.get("lean","unknown") for a in cluster_articles})

    # ── Accuracy signals for Claude ──────────────────────────────
    contradiction_flags = detect_contradictions(cluster_articles)
    prov_ratio          = cluster_provisional_ratio(cluster_articles)
    has_wire            = cluster_has_wire_source(cluster_articles)
    has_intel           = cluster_has_intel_corroboration(cluster_articles)
    diversity_score     = cluster_source_diversity(cluster_articles)
    corroboration       = cluster_corroboration_detail(cluster_articles)
    sid                 = story_id(cluster_articles[0]["title"])
    drift_note, drift_events = detect_narrative_drift(sid)

    # Build accuracy context block for the prompt
    accuracy_context = []
    if contradiction_flags:
        accuracy_context.append("SOURCE CONFLICTS DETECTED:")
        for flag in contradiction_flags:
            accuracy_context.append(f"  ⚠ {flag}")
    # ── Intel + primary-first corroboration assessment ───────────
    # Verification hierarchy: Primary docs > Intel sources > Wire news
    # Mainstream press is TRACKED but does NOT drive confidence.
    # This avoids narrative capture from concentrated media ownership.
    primary_srcs    = corroboration.get("primary_srcs", [])
    intel_srcs      = corroboration.get("intel_srcs", [])
    wire_srcs       = corroboration.get("wire_srcs", [])
    state_srcs      = corroboration.get("state_srcs", [])
    mainstream_srcs = corroboration.get("mainstream_srcs", [])
    corr_count      = corroboration.get("corroboration_count", 0)

    if primary_srcs:
        accuracy_context.append(
            f"PRIMARY DOCUMENT CORROBORATION: {', '.join(primary_srcs[:4])} — "
            f"these are primary evidence (filings, designations, field data), not journalism. "
            f"Treat claims traceable to these as established facts. "
            f"{'Intel also confirms: ' + ', '.join(intel_srcs[:3]) + '.' if intel_srcs else ''}"
        )
    elif len(intel_srcs) >= 3:
        accuracy_context.append(
            f"MULTI-INTEL CORROBORATION: {', '.join(intel_srcs[:4])} — "
            f"independent methodologies (OSINT/investigative/specialist) converge. "
            f"This is strong independent corroboration even without primary documents. "
            f"{'Wire confirms: ' + wire_srcs[0] + '.' if wire_srcs else 'No wire coverage yet — note this.'}"
        )
    elif len(intel_srcs) >= 2:
        accuracy_context.append(
            f"INTEL CORROBORATION: {', '.join(intel_srcs[:3])} independently confirm. "
            f"Confidence ceiling: medium. Not yet primary-document verified. "
            f"{'Wire also covers.' if wire_srcs else 'No wire coverage.'}"
        )
    elif intel_srcs:
        accuracy_context.append(
            f"SINGLE INTEL SOURCE: {intel_srcs[0]} — "
            f"meaningful but needs additional independent corroboration. "
            f"Confidence ceiling: low-medium."
        )
    elif wire_srcs and not intel_srcs and not primary_srcs:
        accuracy_context.append(
            f"WIRE ONLY: {', '.join(wire_srcs[:2])} — "
            f"news confirmed but no independent OSINT, primary document, or investigative verification. "
            f"This means the story exists in mainstream media but its claims are unverified by independent intel. "
            f"Confidence ceiling: low-medium. Do not treat wire coverage as verification of claims."
        )
    elif not primary_srcs and not intel_srcs and not wire_srcs:
        accuracy_context.append(
            "⚠ NO INDEPENDENT CORROBORATION — no primary document, no intel-grade source, no wire. "
            "Social signals or state media only. Confidence ceiling: low."
        )

    # Mainstream is tracked and disclosed but does not drive confidence
    if mainstream_srcs:
        accuracy_context.append(
            f"MAINSTREAM COVERAGE (not used for verification): {', '.join(mainstream_srcs[:4])} — "
            f"these outlets have concentrated ownership and carry packaged narratives. "
            f"Note their coverage but verify all claims against primary docs and intel sources above."
        )

    # State narrative flag
    if state_srcs and not primary_srcs and not intel_srcs:
        accuracy_context.append(
            f"⚠ STATE MEDIA ONLY — {', '.join(state_srcs[:2])} — "
            f"official government claim, not independently verified. "
            f"State media confirms what governments WANT reported."
        )
    elif state_srcs and (primary_srcs or intel_srcs):
        accuracy_context.append(
            f"STATE vs INDEPENDENT DIVERGENCE: {', '.join(state_srcs[:2])} (state narrative) "
            f"vs {', '.join((primary_srcs + intel_srcs)[:3])} (independent). "
            f"Where these diverge IS the story. Surface the gap explicitly."
        )
    if prov_ratio > 0.5:
        accuracy_context.append(f"⚠ {int(prov_ratio*100)}% of sources are <2 hours old — breaking, unverified — use provisional language throughout")
    if drift_note:
        accuracy_context.append(f"NARRATIVE DRIFT DETECTED: {drift_note}")
    if diversity_score >= 60:
        accuracy_context.append(f"Source diversity: high ({diversity_score}/100) — multiple perspectives represented")
    elif diversity_score < 30:
        accuracy_context.append(f"⚠ Source diversity: low ({diversity_score}/100) — limited perspective range")

    accuracy_block = "\n".join(accuracy_context) if accuracy_context else "No conflicts detected across sources."

    # ── Wikipedia entity background for obscure actors ────────────
    # Only run if cluster has entities we might not recognise
    entity_context = ""
    try:
        entity_context = enrich_cluster_with_context(cluster_articles)
    except Exception as e:
        print(f"  Entity context error: {e}")

    # ── Entity connection analysis ────────────────────────────────
    # Extract all named entities across the cluster and find co-occurrences
    # This surfaces hidden connections between actors, locations, organisations
    all_entities = []
    for article in cluster_articles[:8]:
        ents = article.get("entities", "")
        if ents:
            # Parse "PERSON:Araghchi, ORG:IRGC, GPE:Tehran" format
            parts = [p.strip() for p in ents.split(",") if ":" in p]
            for part in parts:
                typ, name = part.split(":", 1)
                all_entities.append((typ.strip(), name.strip()))

    if all_entities:
        # Find entities appearing across multiple sources (cross-source connections)
        from collections import Counter
        ent_counts = Counter(f"{t}:{n}" for t, n in all_entities)
        # Entities mentioned by 3+ articles = connection worth noting
        cross_source_ents = [e for e, count in ent_counts.most_common(10) if count >= 2]
        if cross_source_ents:
            accuracy_context.append(
                f"CROSS-SOURCE ENTITY CONNECTIONS: These actors/locations appear across "
                f"multiple independent sources — {', '.join(cross_source_ents[:8])}. "
                f"Investigate relationships between these entities explicitly."
            )

    # ── Actor structural interest context ─────────────────────────
    actor_context = build_actor_context_block(cluster_articles)
    if actor_context:
        accuracy_context.append(actor_context)

    # ── Cross-article citation network ────────────────────────────
    citations = find_cross_citations(cluster_articles)
    if citations:
        cite_lines = [c["note"] for c in citations]
        accuracy_context.append(
            f"CROSS-CITATION NETWORK: {'; '.join(cite_lines[:4])}. "
            f"Articles citing each other or shared primary documents = stronger corroboration."
        )
        # Find co-occurring persons and organisations (potential financial/political links)
        persons = [n for t, n in all_entities if t == "PERSON"]
        orgs    = [n for t, n in all_entities if t == "ORG"]
        if len(set(persons)) >= 2 and len(set(orgs)) >= 2:
            accuracy_context.append(
                f"KEY ACTORS: {', '.join(list(set(persons))[:5])} | "
                f"KEY ORGS: {', '.join(list(set(orgs))[:5])} — "
                f"identify documented relationships or financial connections between these."
            )
        accuracy_block = "\n".join(accuracy_context) if accuracy_context else "No conflicts detected across sources."

    # ── Pull previous version summaries for narrative comparison ──────────
    # Shows Claude what this story looked like before so it can flag changes
    history   = load_json_file(STORY_HISTORY_FILE, {})
    prev_entry = history.get(sid)
    history_context = ""
    if prev_entry and prev_entry.get("versions"):
        prev_versions = prev_entry["versions"][-4:]  # last 4 versions
        history_context = "\n\nPREVIOUS VERSIONS OF THIS STORY (oldest→newest):\n"
        for i, v in enumerate(prev_versions):
            history_context += f"  v{v.get('version_num','?')} [{v.get('time','?')[:16]}] conf={v.get('confidence','?')}\n"
            history_context += f"    Headline: {v.get('headline','')}\n"
            history_context += f"    Summary: {(v.get('summary',''))[:300]}\n"
            srcs = v.get("sources", [])
            if srcs:
                history_context += f"    Sources: {', '.join(srcs[:6])}\n"
            history_context += "\n"
        if drift_note:
            history_context += f"NARRATIVE DRIFT SUMMARY: {drift_note}\n"
        history_context += (
            "INSTRUCTION: Compare the current articles to these previous versions. "
            "If the headline, confidence, key facts, or source set has materially changed, "
            "note this explicitly in your summary using phrases like: "
            "'This updates previous reporting which stated...', "
            "'Earlier sources claimed X — new wire reporting now indicates Y', "
            "'Confidence has risen/fallen because...'. "
            "If sources previously covering this story are now absent, note that explicitly."
        )

    prompt  = f"""You are Parallax — an intelligence analysis system. Your job is not to produce a confident account of what happened. Your job is to tell the reader what each source says, how much to trust it, and where the sources disagree. You are a detective evaluating evidence, not a journalist summarising events.

ACCURACY SIGNALS (read these before writing anything):
{accuracy_block}
{history_context}
{entity_context}
CRITICAL RULES:
1. Every factual claim must trace to a specific named source in the articles below. No exceptions.
2. You may use background knowledge ONLY to identify who an actor is or what an organisation does — never to assert new facts about this specific event.
3. If sources conflict, the conflict IS the story. Surface it prominently — do not average it away.
4. If no wire service is covering this event, say so explicitly and cap confidence at "low".
5. If sources are mostly <2 hours old, use provisional language throughout: "reportedly", "claimed", "unconfirmed".
6. Social media posts (Reddit, Telegram, Bluesky) are signals, not sources. Treat them as community intelligence, not verified reporting.
7. Source hierarchy for VERIFICATION (not just coverage): Primary documents (IAEA, ICC, OFAC, ACLED, court filings) > Independent OSINT/investigative (Bellingcat, OCCRP, ICIJ, ISW, field specialists) > Wire services (Reuters, AP, AFP) > Mainstream press. Mainstream press covers stories — it does not verify them. A story confirmed only by BBC/CNN/Bloomberg is news coverage, not independent corroboration. A story confirmed by IAEA data + Bellingcat geolocation is independently verified fact.
8. FIND THE CONNECTIONS. Your most important job is to surface relationships the reader would not find by reading mainstream news alone:
   - Who benefits financially from this event? Which specific companies, funds, or individuals?
   - Are any named actors connected to other ongoing stories? (e.g. if a sanctioned person appears, note their sanction history)
   - Is there a pattern across recent events that this story fits into? Name it.
   - What are the SECOND-ORDER consequences — who does this affect beyond the immediate actors?
   - When an independent journalist or investigative outlet is in the sources, their angle often contains the connection mainstream sources miss — weight it accordingly and highlight what they found that others did not.
9. Independent sources (Bellingcat, OCCRP, ICIJ, ProPublica, independent journalists) frequently contradict or go further than wire services. If they do, that gap IS the most important part of the story.
10. ABSENCE IS EVIDENCE. If a major actor is NOT mentioned in the sources, note that. If a wire service is NOT covering something that Bellingcat or a regional specialist IS covering, flag it explicitly as "under-reported by mainstream media."
11. FOR EVERY MAJOR CLAIM — ask three questions then answer them in narrative_analysis:
    A) WHY WOULD THIS ACTOR SAY THIS? What structural interest (military, financial, political survival, domestic legitimacy) does this claim serve for the actor making it? Use the ACTOR STRUCTURAL INTERESTS block above.
    B) WHAT DO THEY LOSE IF IT'S FALSE? What is at stake for the actor if independent verification shows their claim is wrong?
    C) IS THERE PRIMARY DOCUMENT EVIDENCE? Can the claim be checked against IAEA data, ICC filings, OFAC designations, ACLED events, satellite imagery, or leaked documents? State explicitly what primary evidence exists or is absent.
12. NARRATIVE DISCREPANCY DETECTION: When two actors make contradictory claims, do not average them. Instead: state both claims precisely, identify what primary evidence would resolve them, and note which actor has the stronger structural interest in the false version being believed.
13. CONTESTED NUMBERS ARE THE MOST IMPORTANT OUTPUT. For every metric where different sources report different figures (casualties, territory, enrichment levels, barrels of oil, economic growth, refugee counts) — extract ALL versions, attribute each to a specific reporter, state each reporter's methodology and structural incentive to report high or low. The gap between figures is often the story. Make contested_numbers[] the most detailed section of your output.
14. BENEFICIARY TRANSPARENCY: For every conflict, sanction, or major policy event — name the specific companies and financial actors who benefit. "The arms industry" is not sufficient. Name Raytheon, Lockheed Martin, Elbit Systems, or whoever specifically gains contracts or stock value from this outcome.

ARTICLES ({len(cluster_articles)} sources — tiers: {", ".join(list(set(str(get_source_tier(a["source"])) + "=" + a["source"] for a in cluster_articles[:6]))[:4])} — leans: {", ".join(lean_labels[:4])}):
{article_text}

WRITING STYLE:
- Write like a senior analyst briefing an intelligent person who has no specialist background
- Plain English throughout. First use of any abbreviation or technical term: spell it out immediately. Example: "the IMF (International Monetary Fund)" not just "the IMF"
- Every factual sentence must be attributable to a specific source article — if you state something happened, a specific outlet reported it
- Use "according to [Source]", "Reuters reported", "[Source] claimed" to attribute every key fact
- Use "allegedly", "reportedly", "unconfirmed" for anything not corroborated by multiple sources
- Be specific — real names, locations, numbers, dates from the articles
- USE THE NUMBERS: When articles contain specific figures (dollar amounts, casualty counts, percentages), include them. "Significant losses" is useless. "$4.3 billion in asset freezes" is intelligence.
- USE THE QUOTES: When articles contain direct quotes from officials or actors, use them verbatim with attribution. A direct quote is primary evidence. Paraphrasing loses meaning.
- CONTESTED NUMBERS ARE THE MOST IMPORTANT OUTPUT: When different sources report different numbers for the same thing, that discrepancy is often the entire story. Fill contested_numbers for EVERY metric where two or more sources give different values. Examples:
    * Russia says 200 Ukrainian tanks destroyed. Ukraine says 12. → contested_numbers entry with both, plus why each has incentive to report their number
    * Gaza health ministry reports 34,000 killed. Israel disputes the methodology. → two entries with different values, different methodologies, different incentives
    * IMF says GDP growth 2.1%. Government claims 4.3%. → contested_numbers entry with both
    * A company reports $500M in damages. Insurers assess $2.1B. → contested entry
  For each contested number: extract the EXACT value each source gives, name them specifically, explain their counting methodology if known, explain their structural incentive to report high/low, and note whether any primary document resolves it.
- ARTICLE TYPES MATTER: A [CORRECTION] article means something was wrong. A [PRIMARY-DOC] article is higher confidence than [OPINION]. Treat them differently.
- Never pad — every sentence must earn its place. A reader should finish in 90 seconds
- Never start consecutive sentences with the same word
- Do not editoralise — present what sources say, not your assessment of whether it is true
- Where sources disagree, say so explicitly: "Reuters reported X while Al Jazeera reported Y"
- Where a source has a known lean (state media, NATO-aligned), flag it: "according to TASS, Russia's state news agency"
- Social media sources need extra attribution care: "a widely-shared Reddit post in r/CredibleDefense claimed", "according to the Telegram channel War Translated", "Bluesky users reported". Neverr treat social media posts as equivalent to verified reporting — they are signals, not sources
- A Reddit post with 5,000 upvotes is not a primary source — it may link to or discuss a primary source. Cite the underlying source where possible, note the Reddit discussion as corroborating community interest
- Telegram military bloggers (e.g. Rybar, Intel Slava) represent a specific geopolitical perspective — label them clearly: "Russian military blogger Rybar claimed" not just "reported"

Respond with ONLY a JSON object (no markdown):
{{
  "headline": "Factual headline max 15 words — specific not generic",
  "location": "City, Country or Global",
  "region": "europe|middle-east|africa|asia-pacific|americas|russia-fsu|china|global",
  "category": "conflict-war|politics|economics|human-rights|environment|technology|disinformation",
  "confidence": "low|medium|high",
  "summary": "THREE paragraphs, 250-300 words total — a 90-second read. Lead with what happened. Every factual claim must be attributed to a named source (e.g. 'Reuters reported', 'according to Al Jazeera'). Paragraph 1: the news — what happened, who is involved, what is confirmed vs alleged, specific details from the articles. Paragraph 2: the context — what background explains this event, who the key actors are and what they want, what pattern this fits into. Use your knowledge here to explain who actors are but only assert new facts if sourced. Paragraph 3: the significance — who benefits, what changes if this is true, what to watch in the next 48-72 hours. Plain English throughout. Flag where sources disagree.",
  "what_is_known": ["Full sentence stating a verified fact with source", "Full sentence stating another verified fact", "Full sentence stating a third verified fact — add more if available"],
  "what_is_disputed": "Full paragraph explaining what remains unconfirmed, what the competing claims are, and why independent verification is difficult. 2-3 sentences.",
  "contested_numbers": [
    {{
      "metric": "What is being counted/measured — be specific (e.g. 'civilian deaths', 'troops deployed', 'economic damage')",
      "unit": "The unit of measurement (people, USD, km², tonnes, etc.)",
      "claims": [
        {{
          "reporter": "Who is reporting this number — specific actor/source",
          "value": "The exact number or range they report (e.g. '2,300', '$4.7 billion', '15,000–18,000')",
          "value_numeric": 2300,
          "methodology": "How they count or what they include — briefly",
          "incentive": "Why this actor may report higher/lower — their structural interest in this number"
        }}
      ],
      "spread": "The gap between highest and lowest claim — e.g. '13,700-person gap'",
      "ground_truth": "What primary document evidence (IAEA, ACLED, ICC, satellite) says — or null if no primary source exists",
      "why_it_matters": "Why this number discrepancy is strategically important — who benefits from each version being believed"
    }}
  ],
  "who_benefits": {{
    "narrative_a": {{"actor": "Name", "benefit": "Why they benefit from this being true", "level": "high|medium|low"}},
    "narrative_b": {{"actor": "Name", "benefit": "Why they benefit from an alternative framing", "level": "high|medium|low"}},
    "narrative_c": {{"actor": "Name or null", "benefit": "Third party beneficiary if any", "level": "high|medium|low"}},
    "civilian_impact": "How ordinary people — not governments or corporations — are concretely affected."
  }},
  "narrative_analysis": {{
    "competing_narratives": [
      {{
        "source_actor": "Who is pushing this narrative (state, faction, corporation)",
        "narrative": "What they are claiming in one sentence",
        "structural_interest": "What structural interest this claim serves for them",
        "evidence_for": "Primary document or OSINT evidence supporting this claim",
        "evidence_against": "Primary document or OSINT evidence contradicting this claim",
        "verdict": "supported|disputed|unverifiable|state-claim-only"
      }}
    ],
    "narrative_gaps": "What no actor is saying but primary evidence suggests — the silence that is itself a signal",
    "narrative_convergence": "Where competing actors agree — convergence across hostile sources can indicate truth",
    "disinfo_indicators": "Specific features that suggest coordinated narrative management rather than organic reporting"
  }},
  "money_flow": {{
    "financial_interests": "Named entities with documented financial interests in this outcome — be specific.",
    "arms_industry": "Which defence contractors benefit and how — name them",
    "energy_interests": "Which energy companies/states benefit from this outcome",
    "known_flows": ["Specific documented financial flow with source"],
    "data_gaps": "What financial flows are opaque from public data — name the specific gap"
  }},
  "actor_statements": [
    {{
      "actor": "Named actor (state, official, organisation)",
      "claim": "What they specifically said or did",
      "structural_reason": "Why their structural interests lead them to say this",
      "credibility": "high|medium|low|state-claim",
      "contradicted_by": "Primary source or OSINT that contradicts this claim, or null"
    }}
  ],
  "confidence_reason": "One sentence explaining this confidence level.",
  "source_citations": [
    {{"source": "Source name", "platform": "rss|reddit|telegram|bluesky", "lean": "their lean", "url": "article url", "claim": "what this source specifically reported"}}
  ],
  "source_diversity": "brief note on whether sources represent multiple perspectives or are predominantly from one viewpoint",
  "signal_score": 50,
  "velocity_score": 50,
  "contradiction_flags": [],
  "provisional": false
}}"""
    result = call_claude(prompt)
    if not result: return None
    result = result.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    try:
        data = json.loads(result)
        data["id"] = story_id(data.get("headline","") + cluster_articles[0]["published"])
        data["published"] = cluster_articles[0]["published"]
        data["updated"] = utc_now().isoformat()
        data["sources"] = list(sources)[:8]
        data["sources_count"] = len(cluster_articles)
        data["article_urls"] = [a["url"] for a in cluster_articles[:4] if a.get("url")]
        # Attach narrative drift events for Cascade tab
        data["drift_events"]        = drift_events if "drift_events" in dir() else []
        data["drift_note"]          = drift_note   if "drift_note"   in dir() else ""
        # Attach locally-computed metadata for run_scraper to use
        data["_contradiction_flags"] = contradiction_flags if "contradiction_flags" in dir() else []
        data["_prov_ratio"]          = prov_ratio          if "prov_ratio"          in dir() else 0.0
        data["_corroboration"]       = corroboration       if "corroboration"       in dir() else {}
        data["_diversity_score"]     = diversity_score     if "diversity_score"     in dir() else 50
        return data
    except Exception as e:
        print(f"  JSON error: {e}"); return None

# ─────────────────────────────────────────────
# FRED
# ─────────────────────────────────────────────
def fetch_fred(series_id):
    data = fetch_url(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
    if not data: return None
    lines = [l for l in data.strip().split("\n") if l and not l.startswith("DATE")]
    for line in reversed(lines):
        parts = line.split(",")
        if len(parts) >= 2 and parts[1].strip() not in (".", ""):
            try: return {"date": parts[0].strip(), "value": float(parts[1].strip())}
            except: pass
    return None

# ─────────────────────────────────────────────
# MAIN SCRAPER
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# DAILY BRIEF GENERATOR
# ─────────────────────────────────────────────

def generate_daily_brief():
    """
    Generates a structured intelligence brief at 05:00 UTC.
    Uses Claude with web search to pull overnight developments,
    synthesises with current stories.json data, and saves to brief.json.
    """
    print("\n" + "="*50)
    print(f"Daily Brief — {utc_now().strftime('%A %d %B %Y · 05:00 UTC')}")
    print("="*50)

    if not ANTHROPIC_API_KEY:
        print("  Brief: ANTHROPIC_API_KEY not set — skipping")
        return

    # Load current stories for context
    try:
        with open(DATA_FILE) as f:
            current = json.load(f)
        stories = current.get("stories", [])
        story_context = "\n".join(
            f"- {s.get('headline','?')} [{s.get('confidence','?')} confidence, score {s.get('signal_score',0)}]"
            for s in stories[:8]
        )
    except Exception:
        story_context = "No current stories available."

    today = utc_now().strftime("%A %d %B %Y")

    system_prompt = f"""You are Parallax — an intelligence analysis system producing a morning briefing for {today}.

Using your web search tool, search for overnight developments on the most significant current intelligence topics:
- US-Iran war, ceasefire status, Strait of Hormuz
- Ukraine frontline and any overnight Russian strikes or Ukrainian operations
- Sudan/Darfur: RSF activity and humanitarian situation
- Any other major breaking developments overnight

Current tracked stories for context:
{story_context}

Produce a concise, factual morning brief. Every claim must be attributed to a specific source.

Return ONLY a JSON object (no markdown):
{{
  "date": "{today}",
  "generated_at": "05:00 UTC",
  "threat_level": "elevated|high|critical|moderate",
  "threat_level_reason": "One sentence explaining the overall threat assessment for today",
  "headline_brief": "One sentence: the single most significant development overnight",

  "intelligence_overview": {{
    "paragraph_1_situation": "CURRENT SITUATION — 150-200 words. What is the state of the world right now across all tracked theatres. Lead with the most urgent. Name actors, numbers, locations. Every sentence sourced. This is the helicopter view — what a senior analyst would say in the first 60 seconds of a briefing.",
    "paragraph_2_connections": "THE CONNECTIONS — 150-200 words. What links these stories together that the reader would miss reading headlines separately. What pattern runs across the Iran war, Ukraine, Sudan, economic signals? Who are the common actors appearing in multiple theatres? What financial flows connect seemingly separate events? What second-order consequence from Story A is now visible in Story B?",
    "paragraph_3_what_watch": "WHAT TO WATCH TODAY — 150-200 words. The 3-5 most specific, verifiable things that will indicate how today develops. Not general themes — specific actors, specific actions, specific indicators. What primary evidence (IAEA access, vessel movements, OFAC announcement) would confirm or deny each scenario.",
    "paragraph_4_buried": "WHAT MAINSTREAM IS MISSING — 100-150 words. The story that is in the intel sources but not on front pages. What is ACLED tracking that Reuters isn't reporting? What regional specialist published something with zero pickup? What silence from a state actor is itself a signal? This is the paragraph that requires reading between the lines."
  }},

  "top_stories": [
    {{
      "rank": 1,
      "region": "middle-east",
      "story_card_ids": ["story-6", "story-7"],
      "headline": "Specific headline max 15 words — factual not vague",
      "paragraph_1_situation": "180-200 words. What is the current situation for THIS story specifically. Lead with what happened. Every sentence attributed to a named source. Specific actors, numbers, locations. This is the primary factual record.",
      "paragraph_2_connections": "180-200 words. What links THIS story to the other stories in today's brief. Be specific — name the other stories and explain the exact mechanism connecting them. Financial flows, shared actors, causal chains, strategic interactions. This paragraph must reference at least 2 other stories from today.",
      "paragraph_3_watch": "150-180 words. 3-5 specific verifiable things to watch in the next 24 hours for THIS story. Name the actor, the action, and what it would mean. Primary evidence (IAEA statement, vessel count, ISPR release) that would confirm or deny each scenario.",
      "paragraph_4_buried": "120-150 words. What is in the intelligence sources but not in mainstream coverage for THIS story. What is ACLED tracking that Reuters isn't reporting? What silence from a state actor is itself a signal? What technical detail changes the meaning of the headline?",
      "significance": "One sentence: the single most important thing to understand about this story",
      "contested_claim": "If any source disputes another, state both precisely — or null",
      "has_prediction": true,
      "has_psyop": false,
      "has_econ": false,
      "source": "Primary source names"
    }}
  ],

  "overnight_signals": [
    {{
      "signal": "One sentence — actor, action, number",
      "source": "Named source",
      "significance": "brief|moderate|high",
      "story_card_id": "story-1"
    }}
  ],

  "contested_numbers_today": [
    {{
      "metric": "What is being contested",
      "actor_a": "First actor",
      "value_a": "Their figure",
      "actor_b": "Second actor",
      "value_b": "Their figure",
      "why_gap": "One sentence: structural reason for the discrepancy"
    }}
  ],

  "analyst_note": "2-3 sentences: the most important pattern or under-reported story — what requires reading between the lines today",
  "sources_consulted": ["source1", "source2", "source3"]
}}

Include 5-6 top_stories, 5-8 overnight_signals, and 1-3 contested_numbers_today entries.
Map story_card_ids: story-1=Ukraine, story-2=Sudan, story-3=China, story-4=Turkey, story-5=Manipur, story-6=Iran/Hormuz, story-7=Oil/IMF, story-8=Pakistan/Islamabad.
The four intelligence_overview paragraphs are the core analytical product — make them dense, specific, and reveal connections.
"""

    payload = json.dumps({
        "model":      "claude-sonnet-4-6",
        "max_tokens": 16000,
        "system":     system_prompt,
        "messages":   [{"role": "user", "content": f"Generate the Parallax morning brief for {today}. Search for overnight developments now."}],
        "tools":      [{"type": "web_search_20250305", "name": "web_search"}]
    }).encode()

    req = Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )

    try:
        with urlopen(req, timeout=600) as r:
            data = json.loads(r.read())

        text = " ".join(
            b["text"] for b in data.get("content", [])
            if b.get("type") == "text"
        ).strip()

        if not text:
            print("  Brief: No text returned from Claude")
            return

        clean = text.replace("```json","").replace("```","").strip()
        j_start = clean.find("{")
        j_end   = clean.rfind("}") + 1
        json_text = clean[j_start:j_end]

        # v8 robust JSON parse: strict -> repair pass -> debug fallback
        try:
            brief = json.loads(json_text, strict=False)
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
                brief = brief = json.loads(repaired, strict=False)
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

        # Add metadata
        brief["generated_at_iso"] = utc_now().isoformat()
        brief["generated_by"]     = "Parallax daily brief engine v1"

        with open(BRIEF_FILE, "w") as f:
            json.dump(brief, f, indent=2, ensure_ascii=False)

        print(f"  Brief generated: {brief.get('headline_brief','?')[:70]}")
        print(f"  Threat level: {brief.get('threat_level','?')}")
        print(f"  Top stories: {len(brief.get('top_stories',[]))}")

    except Exception as e:
        # Capture full error body from HTTPError for debugging
        err_body = ""
        try:
            if hasattr(e, 'read'):
                err_body = e.read().decode('utf-8', errors='replace')[:800]
        except Exception:
            pass
        print(f"  Brief error: {e}")
        if err_body:
            print(f"  Brief error body: {err_body}")


def run_scraper():
    global last_run
    print(f"\n{'='*50}")
    print(f"Parallax scraper — {utc_now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*50}\n")
    last_run["status"] = "running"

    # 1. Fetch articles
    all_articles = []
    for feed in RSS_FEEDS:
        try:
            arts = fetch_rss(feed)
            all_articles.extend(arts)
            print(f"  {feed['source']}: {len(arts)} articles")
            time.sleep(0.5)
        except Exception as e:
            print(f"  {feed['source']} error: {e}")

    gdelt = fetch_gdelt()
    all_articles.extend(gdelt)
    print(f"  GDELT: {len(gdelt)} articles")

    # ACLED real-time conflict events (if API key configured)
    acled_events = fetch_acled_events(days_back=3)
    all_articles.extend(acled_events)
    if acled_events:
        print(f"  ACLED API: {len(acled_events)} conflict events")

    # ── Social media sources ──────────────────────────────────────
    # Reddit disabled — no PRAW credentials configured
    # reddit_posts = fetch_reddit()
    # all_articles.extend(reddit_posts)

    telegram_msgs = fetch_telegram()
    all_articles.extend(telegram_msgs)

    bluesky_posts = fetch_bluesky()
    all_articles.extend(bluesky_posts)

    print(f"\nTotal: {len(all_articles)} articles")
    platforms = {}
    for a in all_articles:
        p = a.get("platform", "rss")
        platforms[p] = platforms.get(p, 0) + 1
    print(f"  By platform: {platforms}")

    # 2. Cluster
    clusters = cluster(all_articles)
    # A cluster qualifies if it has 2+ sources from 2+ distinct outlets
    # OR if it has a wire source (single wire report is worth investigating)
    # Social-media-only clusters are still included but flagged via velocity score
    good = [c for c in clusters
            if (len(c) >= CLUSTER_MIN_SOURCES
                and len({a["source"] for a in c}) >= 2)
            or cluster_has_wire_source(c)]
    # Sort by quality: wire-sourced clusters first, then by cluster size
    good.sort(key=lambda c: (
        -int(cluster_has_wire_source(c)),
        -cluster_source_diversity(c),
        -len(c)
    ))
    print(f"Clusters: {len(clusters)} total, {len(good)} with 2+ sources")

    # 3. Enrich articles with full bodies, quotes, numbers, article types
    print("  Enriching articles with full body extraction...")
    for cl in good[:MAX_STORIES]:
        enrich_articles(cl)

    # 4. Generate stories
    stories = []
    for i, cl in enumerate(good[:MAX_STORIES]):
        srcs = list({a["source"] for a in cl})
        print(f"  Story {i+1}: {cl[0]['title'][:55]}... ({len(cl)} arts, {len(srcs)} sources)")
        if ANTHROPIC_API_KEY:
            story = generate_story(cl)
            if story:
                # Compute and inject velocity score
                vel_score = score_signal_velocity(cl, story.get("id", ""))
                story["velocity_score"]      = vel_score
                story["contradiction_flags"] = story.pop("_contradiction_flags", [])
                story["provisional"]         = story.pop("_prov_ratio", 0.0) > 0.5
                story["diversity_score"]     = story.pop("_diversity_score", 50)

                # ── Corroboration-based confidence override ─────────
                # Claude assigns confidence based on article content.
                # We override downward if independent corroboration doesn't support it.
                if story.get('_corroboration'):
                    corr = story.pop('_corroboration')
                    claude_conf = story.get("confidence", "low")
                    corr_conf   = corr.get("confidence", "low")
                    conf_order  = {"low": 0, "medium": 1, "high": 2}
                    # Only override downward — don't upgrade past what Claude assessed
                    if conf_order.get(corr_conf, 0) < conf_order.get(claude_conf, 0):
                        story["confidence"]      = corr_conf
                        story["confidence_reason"] = (
                            f"[Downgraded from {claude_conf}] {corr.get('conf_reason','')} | "
                            + story.get("confidence_reason","")
                        )
                    # Attach corroboration breakdown
                    story["corroboration"] = {
                        "wire_sources":  corr.get("wire_srcs", []),
                        "intel_sources": corr.get("intel_srcs", []),
                        "state_sources": corr.get("state_srcs", []),
                        "social_sources":corr.get("social_srcs", []),
                        "count":         corr.get("corroboration_count", 0),
                    }
                # Narrative drift — enhanced multi-signal
                _drift_note, _drift_events = detect_narrative_drift(story.get("id",""))
                story["drift_note"]         = _drift_note
                story["drift_events"]       = _drift_events
                # Full version history for Cascade tab
                _hist = load_json_file(STORY_HISTORY_FILE, {})
                story["version_history"] = _hist.get(story.get("id",""), {}).get("versions", [])
                # Attach full snapshot history for the Cascade tab
                _snaps = load_json_file(NARRATIVE_FILE, {})
                story["narrative_history"]  = _snaps.get(story.get("id",""), {}).get("snapshots", [])
                # Archive high-confidence story sources (best-effort)
                if story.get("confidence") == "high" and story.get("article_urls"):
                    for archive_url in story["article_urls"][:2]:
                        try:
                            archive_result = archive_url_wayback(archive_url)
                            if archive_result:
                                story.setdefault("archived_urls", []).append(archive_result)
                        except Exception:
                            pass

                stories.append(story)
            time.sleep(1.2)
        else:
            # Fallback without API key
            stories.append({
                "id": story_id(cl[0]["title"]),
                "headline": cl[0]["title"][:100],
                "location": "Unknown", "region": "global", "category": "politics",
                "confidence": "low",
                "summary": cl[0].get("summary","")[:250],
                "what_is_known": [f"Reported by {s}" for s in srcs[:3]],
                "what_is_disputed": "Verification pending.",
                "who_benefits": {"narrative_a":{"actor":"Unknown","benefit":"Under analysis","level":"low"},
                                 "narrative_b":{"actor":"Unknown","benefit":"Under analysis","level":"low"},
                                 "civilian_impact":"Under analysis."},
                "money_flow": {"financial_interests":"Under analysis.","known_flows":[],"data_gaps":"Unknown."},
                "confidence_reason": "Early report — insufficient independent sources.",
                "signal_score": min(25 + len(cl) * 5, 65),
                "published": cl[0]["published"],
                "updated": utc_now().isoformat(),
                "sources": srcs[:8], "sources_count": len(cl),
                "article_urls": [a["url"] for a in cl[:3] if a.get("url")]
            })

    # 4. FRED signals
    print("\nFetching FRED economic signals...")
    econ = {}
    for key, series in FRED_SERIES.items():
        val = fetch_fred(series)
        if val:
            econ[key] = val
            print(f"  {key}: {val['value']} ({val['date']})")
        time.sleep(0.4)

    # 4b. Save velocity and narrative history
    save_velocity_record(stories)
    save_narrative_snapshot(stories)

    # 4c. Absence detection — ACLED events with no wire coverage
    absence_alerts = check_absence_detection(all_articles)
    if absence_alerts:
        print(f"  Absence alerts: {len(absence_alerts)} underreported events detected")

    # 5. Write output
    output = {
        "generated_at": utc_now().isoformat(),
        "story_count": len(stories),
        "stories": stories,
        "economic_signals": econ,
        "absence_alerts": absence_alerts if 'absence_alerts' in dir() else [],
        "meta": {
            "articles_processed": len(all_articles),
            "clusters_found": len(clusters),
            "clusters_qualified": len(good),
            "scrape_interval_minutes": SCRAPE_INTERVAL_MINUTES,
            "api_key_present": bool(ANTHROPIC_API_KEY)
        }
    }
    with open(DATA_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    last_run = {
        "time": utc_now().isoformat(),
        "stories": len(stories),
        "articles": len(all_articles),
        "status": "ok"
    }
    print(f"\n✓ Done — {len(stories)} stories written to {DATA_FILE}")

# ─────────────────────────────────────────────
# BACKGROUND SCHEDULER
# ─────────────────────────────────────────────
def scheduler():
    """
    Background scheduler:
    - Runs scraper every SCRAPE_INTERVAL_MINUTES
    - Generates daily brief at BRIEF_HOUR_UTC:00 UTC
    """
    last_brief_date = None

    # First run immediately on start
    try:
        run_scraper()
    except Exception as e:
        import traceback
        print(f"Scraper error: {e}")
        print(traceback.format_exc())
        last_run["status"] = f"error: {e}"

    while True:
        time.sleep(60)  # Check every minute for brief trigger

        now = utc_now()

        # ── Daily brief at 05:00 UTC ──────────────────────────────
        if (now.hour == BRIEF_HOUR_UTC
                and now.minute < 2
                and last_brief_date != now.date()):
            last_brief_date = now.date()
            try:
                generate_daily_brief()
            except Exception as e:
                print(f"Brief error: {e}")

        # ── Scraper every N minutes ───────────────────────────────
        last_time_str = last_run.get("time")
        if last_time_str:
            elapsed = (now - datetime.fromisoformat(last_time_str)).total_seconds() / 60
        else:
            elapsed = SCRAPE_INTERVAL_MINUTES + 1  # never ran → trigger now

        if elapsed >= SCRAPE_INTERVAL_MINUTES:
            try:
                run_scraper()
            except Exception as e:
                import traceback
                print(f"Scraper error: {e}")
                print(traceback.format_exc())
                last_run["status"] = f"error: {e}"


# ─────────────────────────────────────────────
# FLASK WEB SERVER
# ─────────────────────────────────────────────
if FLASK:
    app = Flask(__name__, static_folder=".", static_url_path="")

    @app.route("/")
    def index():
        return send_file("parallax.html")

    @app.route("/stories.json")
    def stories():
        if not os.path.exists(DATA_FILE):
            return jsonify({"generated_at": utc_now().isoformat(),
                           "story_count": 0, "stories": [],
                           "economic_signals": {}, "meta": {"status": "generating"}})
        return send_file(DATA_FILE, mimetype="application/json")

    @app.route("/sources.json")
    def sources_json():
        # Group RSS_FEEDS by lean into tiers for the frontend Source Registry
        tier_map = {
            # Wires & mainstream
            "centre": ("Wires & mainstream", "t1"),
            "centre-left": ("Wires & mainstream", "t1"),
            "centre-right": ("Wires & mainstream", "t1"),
            "financial-centre": ("Wires & mainstream", "t1"),
            "independent": ("Wires & mainstream", "t1"),
            # Primary documents & official
            "primary-document": ("Primary documents", "t1"),
            "multilateral": ("Primary documents", "t1"),
            "us-government": ("Primary documents", "t1"),
            # Policy & think tanks
            "us-foreign-policy": ("Policy & think tanks", "t1"),
            "think-tank": ("Policy & think tanks", "t1"),
            "uk-analytical": ("Policy & think tanks", "t1"),
            "nato-aligned": ("Policy & think tanks", "t1"),
            # Investigative & OSINT
            "investigative-osint": ("Investigative & OSINT", "t2"),
            "osint": ("Investigative & OSINT", "t2"),
            "left-investigative": ("Investigative & OSINT", "t2"),
            "investigative": ("Investigative & OSINT", "t2"),
            # Conflict analysis
            "analytical": ("Conflict analysis", "t2"),
            "arms-research": ("Conflict analysis", "t2"),
            "defence-analytical": ("Conflict analysis", "t2"),
            "conflict-analysis": ("Conflict analysis", "t2"),
            "conflict-data": ("Conflict analysis", "t2"),
            "military": ("Conflict analysis", "t2"),
            "russia-critical": ("Conflict analysis", "t2"),
            # Humanitarian & human rights
            "humanitarian": ("Humanitarian & human rights", "t2"),
            "human-rights": ("Humanitarian & human rights", "t2"),
            # Regional specialist
            "regional": ("Regional specialist", "t2"),
            "regional-specialist": ("Regional specialist", "t2"),
            "china-hk": ("Regional specialist", "t2"),
            "pan-african": ("Regional specialist", "t2"),
            "pakistan-press": ("Regional specialist", "t2"),
            "saudi-aligned": ("Regional specialist", "t2"),
            "israel-centre": ("Regional specialist", "t2"),
            "israel-left": ("Regional specialist", "t2"),
            "iran-independent": ("Regional specialist", "t2"),
            "iran-opposition": ("Regional specialist", "t2"),
            "indian-nationalist": ("Regional specialist", "t2"),
            # State media (monitored for narrative)
            "state-russia": ("State media (monitored)", "t3"),
            "state-china": ("State media (monitored)", "t3"),
            "state-iran": ("State media (monitored)", "t3"),
            "state-israel": ("State media (monitored)", "t3"),
            "russian-state": ("State media (monitored)", "t3"),
            "chinese-state": ("State media (monitored)", "t3"),
            "iran-state": ("State media (monitored)", "t3"),
            # Open event aggregators
            "aggregator": ("Open event aggregators", "t3"),
        }
        grouped = {}
        for f in RSS_FEEDS:
            lean = f.get("lean", "centre")
            group_name, tier = tier_map.get(lean, ("Other sources", "t2"))
            grouped.setdefault(group_name, {"name": group_name, "tier": tier, "sources": []})
            grouped[group_name]["sources"].append({
                "name": f.get("source", "unknown"),
                "meta": "rss \u00b7 " + lean,
            })
        return jsonify({"groups": list(grouped.values())})

    @app.route("/status")
    def status():
        return jsonify(last_run)

    @app.route("/trigger")
    def trigger():
        """Manual scrape trigger — visit /trigger to force a fresh run"""
        t = threading.Thread(target=run_scraper, daemon=True)
        t.start()
        return jsonify({"status": "triggered", "message": "Scraper started in background"})

    @app.route("/brief.json")
    def brief_json():
        """Serve the latest daily brief"""
        try:
            return send_file(BRIEF_FILE, mimetype="application/json")
        except FileNotFoundError:
            return jsonify({"error": "No brief available yet — generates at 05:00 UTC daily"}), 404

    @app.route("/story-history.json")
    def story_history_json():
        """Serve the full story version history"""
        try:
            return send_file(STORY_HISTORY_FILE, mimetype="application/json")
        except FileNotFoundError:
            return jsonify({}), 200

    @app.route("/trigger-brief")
    def trigger_brief():
        """Manual brief trigger for testing"""
        t = threading.Thread(target=generate_daily_brief, daemon=True)
        t.start()
        return jsonify({"status": "triggered", "message": "Brief generation started"})

    @app.route("/debug-brief")
    def debug_brief():
        """Serves latest brief debug files. Query: ?file=raw|repaired, ?pos=<char>, ?ctx=<radius>"""
        import glob as _glob, os as _os
        kind = request.args.get("file", "raw")
        pos  = request.args.get("pos", type=int)
        ctx  = request.args.get("ctx", default=200, type=int)
        pattern = f"brief-{kind}-*.txt"
        files = sorted(_glob.glob(pattern), key=_os.path.getmtime, reverse=True)
        if not files:
            return jsonify({"error": f"no {pattern} files found"}), 404
        latest = files[0]
        try:
            with open(latest, "r", encoding="utf-8") as f:
                data = f.read()
        except Exception as e:
            return jsonify({"error": str(e), "file": latest}), 500
        out = {"file": latest, "size_chars": len(data), "all_files": files[:10]}
        if pos is not None:
            lo = max(0, pos - ctx)
            hi = min(len(data), pos + ctx)
            out["pos"] = pos
            out["context"] = data[lo:hi]
            out["char_at_pos"] = data[pos] if pos < len(data) else None
            out["ord_at_pos"] = ord(data[pos]) if pos < len(data) else None
        else:
            out["preview_start"] = data[:500]
            out["preview_end"]   = data[-500:]
        return jsonify(out)

    @app.route("/research", methods=["POST"])
    def research():
        """
        Research endpoint — accepts a query, calls Claude with web search,
        returns a Parallax story card JSON.
        Called by the browser research bar to avoid CORS issues.
        """
        if not FLASK:
            return jsonify({"error": "Flask not available"}), 503

        try:
            body  = json.loads(request.data or b"{}")
            query = (body.get("query") or "").strip()
            if not query:
                return jsonify({"error": "No query provided"}), 400
            if not ANTHROPIC_API_KEY:
                return jsonify({"error": "ANTHROPIC_API_KEY not set in Replit Secrets"}), 503

            system_prompt = f"""You are Parallax — an intelligence analysis system. A user has searched for: "{query}"

Using your web search tool, find the most recent relevant information from multiple sources. Generate a structured intelligence story card.

RULES:
- Search from multiple angles: what is happening, key actors, disputed claims
- Prioritise news from the last 7 days
- Every factual claim must be attributed to a named source
- Flag anything unverified or contested

Assign ONE category: conflict-war | politics | economics | human-rights | environment | technology | disinformation
Assign ONE region: europe | middle-east | africa | asia-pacific | americas | russia-fsu | china | global

Return ONLY a JSON object (no markdown, no preamble):
{{
  "headline": "Specific factual headline max 15 words",
  "location": "City, Country or Region",
  "region": "one of the regions above",
  "category": "one of the categories above",
  "confidence": "low|medium|high",
  "summary": "Three paragraphs 250-300 words total. Para 1: what is happening with specific attribution. Para 2: context, key actors and their interests. Para 3: what to watch next. Every factual claim attributed to a named source.",
  "what_is_known": ["Verified fact from source", "Verified fact from source", "Verified fact from source"],
  "what_is_disputed": "What remains unconfirmed and why.",
  "confidence_reason": "One sentence explaining confidence level.",
  "signal_score": 50,
  "sources": ["Source 1", "Source 2"],
  "source_citations": [{{"source": "Name", "url": "url", "claim": "what they reported"}}]
}}"""

            payload = json.dumps({
                "model":      "claude-sonnet-4-6",
                "max_tokens": 2000,
                "system":     system_prompt,
                "messages":   [{"role": "user", "content": f"Research and generate a story card for: {query}"}],
                "tools":      [{"type": "web_search_20250305", "name": "web_search"}]
            }).encode()

            req = Request(
                "https://api.anthropic.com/v1/messages",
                data=payload,
                headers={
                    "Content-Type":      "application/json",
                    "x-api-key":         ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01"
                },
                method="POST"
            )

            with urlopen(req, timeout=45) as r:
                data = json.loads(r.read())

            # Extract text blocks (web search responses include tool_use blocks)
            text = " ".join(
                b["text"] for b in data.get("content", [])
                if b.get("type") == "text"
            ).strip()

            if not text:
                return jsonify({"error": "No content returned — try a more specific query"}), 500

            # Parse JSON from response
            clean = text.replace("```json","").replace("```","").strip()
            j_start = clean.find("{")
            j_end   = clean.rfind("}") + 1
            if j_start < 0:
                return jsonify({"error": "Could not parse story JSON"}), 500

            story = json.loads(clean[j_start:j_end])
            story["research_query"] = query
            return jsonify({"ok": True, "story": story})

        except Exception as e:
            print(f"  /research error: {e}")
            return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# SUPPLEMENTARY DATA SOURCES
# ─────────────────────────────────────────────

def fetch_wikipedia_context(entity_name, max_chars=400):
    """
    Fetch Wikipedia summary for a named entity.
    Used to give Claude background on actors it may not recognise.
    Rate-limited: Wikipedia API allows ~200 req/sec, we use <1/sec.
    """
    if not entity_name or len(entity_name) < 3:
        return None
    try:
        params = {
            "action": "query",
            "format": "json",
            "titles": entity_name,
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "exsentences": 3,
        }
        url = "https://en.wikipedia.org/w/api.php?" + urlencode(params)
        data = fetch_url(url, timeout=8)
        if not data: return None
        pages = json.loads(data).get("query",{}).get("pages",{})
        for page in pages.values():
            extract = page.get("extract","").strip()
            if extract and not extract.startswith("REDIRECT"):
                return extract[:max_chars]
        return None
    except Exception:
        return None

def fetch_wikidata_links(entity_name):
    """
    Get Wikidata ID and key properties for a named entity.
    Returns: {"qid": "Q123", "description": "...", "instance_of": "..."}
    Useful for disambiguating people/orgs with similar names.
    """
    if not entity_name: return {}
    try:
        params = {
            "action": "wbsearchentities",
            "search": entity_name,
            "language": "en",
            "format": "json",
            "limit": 1,
        }
        url = "https://www.wikidata.org/w/api.php?" + urlencode(params)
        data = fetch_url(url, timeout=8)
        if not data: return {}
        results = json.loads(data).get("search",[])
        if results:
            r = results[0]
            return {
                "qid": r.get("id",""),
                "description": r.get("description",""),
                "label": r.get("label",""),
            }
        return {}
    except Exception:
        return {}

def fetch_acled_events(country=None, days_back=7):
    """
    Fetch recent conflict events from ACLED API.
    Requires ACLED_API_KEY and ACLED_EMAIL in environment.
    Returns structured conflict event data with fatality counts.
    """
    api_key = os.environ.get("ACLED_API_KEY")
    email   = os.environ.get("ACLED_EMAIL")
    if not api_key or not email:
        return []

    from datetime import date
    end_date   = date.today().isoformat()
    start_date = (date.today() - timedelta(days=days_back)).isoformat()

    params = {
        "key":          api_key,
        "email":        email,
        "event_date":   f"{start_date}|{end_date}",
        "event_date_where": "BETWEEN",
        "limit":        50,
        "fields":       "event_date|event_type|country|location|fatalities|actor1|actor2|notes|source",
        "format":       "json",
    }
    if country:
        params["country"] = country

    data = fetch_url("https://api.acleddata.com/acled/read?" + urlencode(params), timeout=20)
    if not data: return []
    try:
        events = json.loads(data).get("data", [])
        # Convert to article format for clustering
        articles = []
        for e in events:
            fat = int(e.get("fatalities",0) or 0)
            title = f"ACLED: {e.get('event_type','')} in {e.get('location','')}, {e.get('country','')} — {fat} fatalities"
            notes = e.get("notes","")[:300]
            articles.append({
                "title":     title,
                "summary":   notes,
                "url":       "",
                "source":    "ACLED",
                "lean":      "primary-document",
                "published": e.get("event_date", utc_now().isoformat()),
                "text":      f"{title}. {notes}",
                "body":      notes,
                "entities":  f"People: {e.get('actor1','')}, {e.get('actor2','')} | Locations: {e.get('location','')}, {e.get('country','')}",
                "platform":  "acled-api",
                "fatalities": fat,
                "event_type": e.get("event_type",""),
                "country":    e.get("country",""),
                "location":   e.get("location",""),
            })
        return articles
    except Exception as e:
        print(f"  ACLED API error: {e}")
        return []

def enrich_cluster_with_context(cluster_articles):
    """
    For a cluster about to be sent to Claude:
    1. Identify key named entities from article titles
    2. Fetch Wikipedia summaries for unknown/obscure actors
    3. Return a context block to inject into the prompt

    This helps Claude understand: who is IRGC? what is SIPRI?
    what happened in Manipur? — without relying on training data alone.
    """
    # Extract key named entities from all titles
    all_titles = " ".join(a.get("title","") for a in cluster_articles)
    # Proper nouns: capitalised, 3+ chars, not at sentence start
    candidates = set(re.findall(r'(?<=[\w\s])([A-Z][a-z]{2,}(?:\s[A-Z][a-z]{2,})*)', all_titles))
    # Filter obvious common words
    skip = {"The", "This", "That", "These", "Those", "When", "Where", "Which",
            "What", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday", "January", "February", "March", "April",
            "May", "June", "July", "August", "September", "October", "November",
            "December", "United", "States", "State", "New", "War", "News"}
    candidates = {c for c in candidates if c not in skip and len(c) > 4}

    context_parts = []
    for entity in list(candidates)[:5]:  # max 5 lookups per cluster
        wiki = fetch_wikipedia_context(entity, max_chars=200)
        if wiki:
            context_parts.append(f"  {entity}: {wiki}")
        time.sleep(0.3)  # polite rate limiting

    if context_parts:
        return "ENTITY BACKGROUND (Wikipedia):\n" + "\n".join(context_parts)
    return ""




if __name__ == "__main__":
    print("Parallax starting...")
    print(f"API key: {'present' if ANTHROPIC_API_KEY else 'NOT SET — stories will be basic'}")
    print(f"Scrape interval: every {SCRAPE_INTERVAL_MINUTES} minutes")

    # Flask is required — must be in requirements.txt
    if not FLASK:
        raise SystemExit("ERROR: Flask not installed. Add 'flask' to requirements.txt")

    # Start scraper in background thread
    scraper_thread = threading.Thread(target=scheduler, daemon=True)
    scraper_thread.start()
    print("Background scraper started")

    # Start web server
    port = int(os.environ.get("PORT", 8080))
    print(f"Web server starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
