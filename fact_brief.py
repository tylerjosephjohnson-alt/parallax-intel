"""Fact-only daily brief.

An item enters the brief only when at least two independent news or OSINT
outlets reported it, or when a measurement institution recorded it.
State and government outlets are quoted as statements and do not count as
confirmation. Satellite scenes are listed as files on record. They are not
interpreted. Copernicus map products are included only as that service
published them.

The wording around each item is a template. Source headlines are copied,
not rewritten.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

NEWS_LOOKBACK_HOURS = 36
SENSOR_LOOKBACK_HOURS = 72
EMS_LOOKBACK_HOURS = 240
MAX_PER_FEED = 12
MAX_EVENTS = 40
MAX_ENVIRONMENT_EVENTS = 5
MAX_SINGLE = 24
MAX_STATEMENTS = 12
# Keep room for priority singles so war volume cannot wipe economy/persecution.
SINGLE_TOPIC_FLOOR = {
    "conflict-war": 5,
    "economics": 5,
    "persecution": 3,
    "stability": 3,
}
USER_AGENT = "VantageFactBrief/1.0"

# Higher score = higher in the brief. Environment sensors stay in the brief,
# but war, economy, persecution, and stability come first.
TOPIC_PRIORITY = {
    "conflict-war": 500,
    "persecution": 450,
    "stability": 400,
    "economics": 350,
    "politics": 200,
    "environment": 50,
    "other": 20,
}

WAR_TERMS = (
    "war", "warfare", "armed conflict", "conflict", "battlefield", "offensive",
    "airstrike", "air strike", "missile", "drone strike", "artillery", "ceasefire",
    "invasion", "occupied", "front line", "frontline", "militia", "insurgent",
    "combat", "shelling", "troops", "armed forces", "military base", "hostage",
    "attack", "killed", "drone attack", "missile attack", "rocket attack",
    "mortar", "bombardment", "ground offensive", "air raid", "warplane", "fighter jet",
)
PERSECUTION_TERMS = (
    "persecution", "persecuted", "genocide", "ethnic cleansing", "mass detention",
    "detention camp", "forced labor", "forced labour", "human rights", "crackdown",
    "political prisoner", "prisoner of conscience", "refugee", "asylum", "deportation",
    "expelled", "pogrom", "atrocity", "war crime", "crimes against humanity",
    "torture", "disappeared", "extrajudicial", "lynching", "sectarian",
)
STABILITY_TERMS = (
    "coup", "martial law", "state of emergency", "government collapse",
    "no-confidence", "impeachment", "regime", "diplomatic",
    "ambassador", "nuclear", "proliferation", "alliance", "nato", "unrest",
    "riots", "uprising", "insurrection", "secession", "sovereignty",
    "border clash", "mobilization", "mobilisation", "conscription",
    "power grid", "blackout", "martial", "resolution", "security council",
)
# Checked before war so oil, markets, inflation, and defence budgets are not
# swallowed by words like "attack", "missile", or "nato".
ECONOMY_TERMS = (
    # oil & energy markets
    "oil", "brent", "wti", "opec", "crude", "barrel", "oilfield", "oil field",
    "drilling", "petrodollar", "natural gas", "lng", "fuel price", "gas price",
    "energy price", "energy crisis", "petrol", "gasoline", "diesel",
    # inflation / rates / banks
    "inflation", "cpi", "consumer price", "cost of living", "interest rate",
    "rate hike", "rate cut", "raises rates", "raise rates", "cut rates",
    "central bank", "federal reserve", "the fed", "fed",
    "ecb", "bank of england", "bank of japan", "boe", "boj",
    # markets & equities
    "stock market", "stocks", "equities", "equity market", "bond market",
    "bonds", "financial market", "global market", "market rally", "market crash",
    "sell-off", "selloff", "dow jones", "s&p", "nasdaq", "ftse", "nikkei",
    "msci", "futures", "investor", "investors",
    # growth / trade / currency
    "gdp", "recession", "tariff", "trade war", "trade deal", "exports", "imports",
    "currency", "forex", "exchange rate", "dollar index", "yuan", "sanctions",
    # fiscal / war budgets
    "budget", "fiscal", "deficit", "bailout", "imf", "world bank", "debt default",
    "military spending", "defence spending", "defense spending", "military budget",
    "defence budget", "defense budget", "arms spending", "war budget",
    "nato spending", "defence stock", "defense stock", "defence stocks",
    "defense stocks", "arms maker", "arms makers",
    # commodities / logistics
    "commodity", "commodities", "wheat", "grain", "shipping", "supply chain",
    "unemployment", "shipping lane", "grain corridor",
)

# Approximate gazetteer points are used only to decide whether an instrument
# reading is near a reported place. They are not shown as measurements.
GAZETTEER = {
    "afghanistan": (33.9, 67.7), "albania": (41.2, 20.2), "algeria": (28.0, 1.7),
    "argentina": (-38.4, -63.6), "armenia": (40.1, 45.0), "australia": (-25.3, 133.8),
    "austria": (47.5, 14.6), "azerbaijan": (40.1, 47.6), "bangladesh": (23.7, 90.4),
    "belarus": (53.7, 27.9), "belgium": (50.5, 4.5), "bolivia": (-16.3, -63.6),
    "bosnia": (43.9, 17.7), "brazil": (-14.2, -51.9), "bulgaria": (42.7, 25.5),
    "burkina faso": (12.3, -1.6), "cambodia": (12.6, 105.0), "cameroon": (7.4, 12.4),
    "canada": (56.1, -106.3), "chad": (15.5, 18.7), "chile": (-35.7, -71.5),
    "china": (35.9, 104.2), "colombia": (4.6, -74.3), "congo": (-0.2, 15.8),
    "cuba": (21.5, -78.0), "cyprus": (35.1, 33.4), "czechia": (49.8, 15.5),
    "denmark": (56.3, 9.5), "ecuador": (-1.8, -78.2), "egypt": (26.8, 30.8),
    "ethiopia": (9.1, 40.5), "finland": (61.9, 25.7), "france": (46.2, 2.2),
    "georgia": (42.3, 43.4), "germany": (51.2, 10.5), "ghana": (7.9, -1.0),
    "greece": (39.1, 21.8), "haiti": (18.97, -72.3), "hungary": (47.2, 19.5),
    "india": (20.6, 79.0), "indonesia": (-0.8, 113.9), "iran": (32.4, 53.7),
    "iraq": (33.2, 43.7), "ireland": (53.1, -8.0), "israel": (31.0, 34.9),
    "italy": (41.9, 12.6), "japan": (36.2, 138.3), "jordan": (30.6, 36.2),
    "kazakhstan": (48.0, 68.0), "kenya": (0.0, 37.9), "kosovo": (42.6, 20.9),
    "kuwait": (29.3, 47.5), "kyrgyzstan": (41.2, 74.8), "laos": (19.9, 102.5),
    "lebanon": (33.9, 35.9), "libya": (26.3, 17.2), "lithuania": (55.2, 23.9),
    "madagascar": (-18.8, 46.9), "malaysia": (4.2, 101.9), "mali": (17.6, -4.0),
    "mexico": (23.6, -102.5), "moldova": (47.4, 28.4), "mongolia": (46.9, 103.8),
    "morocco": (31.8, -7.1), "mozambique": (-18.7, 35.5), "myanmar": (21.9, 95.9),
    "nepal": (28.4, 84.1), "netherlands": (52.1, 5.3), "new zealand": (-40.9, 174.9),
    "niger": (17.6, 8.1), "nigeria": (9.1, 8.7), "north korea": (40.3, 127.5),
    "norway": (60.5, 8.5), "pakistan": (30.4, 69.3), "panama": (8.5, -80.8),
    "peru": (-9.2, -75.0), "philippines": (12.9, 121.8), "poland": (51.9, 19.1),
    "portugal": (39.4, -8.2), "qatar": (25.4, 51.2), "romania": (45.9, 24.97),
    "russia": (61.5, 105.3), "rwanda": (-1.9, 29.9), "saudi arabia": (23.9, 45.1),
    "senegal": (14.5, -14.5), "serbia": (44.0, 21.0), "somalia": (5.2, 46.2),
    "south africa": (-30.6, 22.9), "south korea": (35.9, 127.8), "south sudan": (6.9, 31.3),
    "spain": (40.5, -3.7), "sri lanka": (7.9, 80.8), "sudan": (12.9, 30.2),
    "sweden": (60.1, 18.6), "switzerland": (46.8, 8.2), "syria": (34.8, 39.0),
    "taiwan": (23.7, 121.0), "tajikistan": (38.9, 71.3), "tanzania": (-6.4, 34.9),
    "thailand": (15.9, 100.9), "tunisia": (33.9, 9.5), "turkey": (39.0, 35.2),
    "turkmenistan": (38.97, 59.6), "uganda": (1.4, 32.3), "ukraine": (48.4, 31.2),
    "united arab emirates": (23.4, 53.8), "united kingdom": (55.4, -3.4),
    "united states": (39.8, -98.6), "uzbekistan": (41.4, 64.6), "vanuatu": (-15.4, 166.9),
    "venezuela": (6.4, -66.6), "vietnam": (14.1, 108.3), "yemen": (15.6, 48.5),
    "zambia": (-13.1, 27.8), "zimbabwe": (-19.0, 29.2),
    "gaza": (31.5, 34.5), "rafah": (31.3, 34.2), "tel aviv": (32.1, 34.8),
    "jerusalem": (31.8, 35.2), "haifa": (32.8, 35.0), "beirut": (33.9, 35.5),
    "damascus": (33.5, 36.3), "aleppo": (36.2, 37.2), "idlib": (35.9, 36.6),
    "baghdad": (33.3, 44.4), "mosul": (36.3, 43.1), "tehran": (35.7, 51.4),
    "isfahan": (32.7, 51.7), "sanaa": (15.4, 44.2), "aden": (12.8, 45.0),
    "riyadh": (24.7, 46.7), "doha": (25.3, 51.5), "dubai": (25.2, 55.3),
    "kyiv": (50.5, 30.5), "kharkiv": (49.99, 36.2), "odesa": (46.5, 30.7),
    "donetsk": (48.0, 37.8), "kherson": (46.6, 32.6), "zaporizhzhia": (47.8, 35.2),
    "crimea": (45.3, 34.0), "moscow": (55.8, 37.6), "st petersburg": (59.9, 30.3),
    "minsk": (53.9, 27.6), "warsaw": (52.2, 21.0), "bucharest": (44.4, 26.1),
    "ankara": (39.9, 32.9), "istanbul": (41.0, 29.0), "cairo": (30.0, 31.2),
    "khartoum": (15.5, 32.5), "el fasher": (13.6, 25.4), "darfur": (13.0, 25.0),
    "addis ababa": (9.0, 38.7), "mogadishu": (2.0, 45.3), "nairobi": (-1.3, 36.8),
    "lagos": (6.5, 3.4), "abuja": (9.1, 7.5), "bamako": (12.6, -8.0),
    "taipei": (25.0, 121.5), "beijing": (39.9, 116.4), "shanghai": (31.2, 121.5),
    "hong kong": (22.3, 114.2), "tokyo": (35.7, 139.7), "seoul": (37.6, 127.0),
    "pyongyang": (39.0, 125.8), "manila": (14.6, 121.0), "jakarta": (-6.2, 106.8),
    "new delhi": (28.6, 77.2), "mumbai": (19.1, 72.9), "islamabad": (33.7, 73.1),
    "karachi": (24.9, 67.0), "kabul": (34.5, 69.2), "dhaka": (23.8, 90.4),
    "port-olry": (-15.0, 167.1), "port vila": (-17.7, 168.3),
    "los angeles": (34.1, -118.2), "san francisco": (37.8, -122.4),
    "california": (36.8, -119.4), "florida": (27.7, -81.5), "texas": (31.0, -99.0),
    "hawaii": (19.9, -155.6), "alaska": (64.2, -152.5),
    "london": (51.5, -0.1), "paris": (48.9, 2.3), "berlin": (52.5, 13.4),
    "rome": (41.9, 12.5), "madrid": (40.4, -3.7), "brussels": (50.8, 4.4),
    "geneva": (46.2, 6.1), "vienna": (48.2, 16.4), "mexico city": (19.4, -99.1),
    "brasilia": (-15.8, -47.9), "sao paulo": (-23.6, -46.6), "bogota": (4.7, -74.1),
    "caracas": (10.5, -66.9), "lima": (-12.0, -77.0),
}

LARGE_PLACES = {
    "australia", "brazil", "canada", "china", "india", "indonesia",
    "russia", "united states",
}

CLASS_TERMS = (
    ("earthquake", ("earthquake", "quake", "seismic")),
    ("fire", ("wildfire", "bushfire", "forest fire")),
    ("volcano", ("volcano", "volcanic")),
    ("storm", ("hurricane", "typhoon", "cyclone", "tropical storm", "tropical depression")),
    ("flood", ("flood", "flooding")),
    ("landslide", ("landslide", "mudslide")),
)

DISTANCE_KM = {
    "earthquake": 250,
    "fire": 80,
    "volcano": 80,
    "storm": 500,
    "flood": 120,
    "landslide": 80,
}

STOPWORDS = {
    "after", "amid", "around", "been", "being", "from", "have", "into", "more",
    "over", "said", "says", "that", "their", "there", "this", "with", "will",
    "would", "about", "against", "before", "between", "could", "during", "other",
    "since", "under", "where", "which", "while", "year", "years", "today",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
}

# standing: report counts toward corroboration; statement is attributed only;
# record is an instrument or mapping institution and can stand alone.
FACT_FEEDS = [
    {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "source": "BBC", "org": "bbc", "standing": "report"},
    {"url": "https://www.france24.com/en/rss", "source": "France 24", "org": "france24", "standing": "report"},
    {"url": "https://rss.dw.com/rdf/rss-en-world", "source": "DW", "org": "dw", "standing": "report"},
    {"url": "https://www.aljazeera.com/xml/rss/all.xml", "source": "Al Jazeera", "org": "aljazeera", "standing": "report"},
    {"url": "https://www.theguardian.com/world/rss", "source": "The Guardian", "org": "guardian", "standing": "report"},
    {"url": "https://feeds.npr.org/1004/rss.xml", "source": "NPR", "org": "npr", "standing": "report"},
    {"url": "https://www.pbs.org/newshour/feeds/rss/world", "source": "PBS NewsHour", "org": "pbs", "standing": "report"},
    {"url": "https://www.abc.net.au/news/feed/51120/rss.xml", "source": "ABC Australia", "org": "abc-au", "standing": "report"},
    {"url": "https://www.cbc.ca/webfeed/rss/rss-world", "source": "CBC", "org": "cbc", "standing": "report"},
    {"url": "https://www.euronews.com/rss?format=mrss&level=theme&name=news", "source": "Euronews", "org": "euronews", "standing": "report"},
    {"url": "https://www.rferl.org/api/zmgqoe$moi", "source": "RFE/RL", "org": "rferl", "standing": "report"},
    {"url": "https://www.thehindu.com/news/international/feeder/default.rss", "source": "The Hindu", "org": "hindu", "standing": "report"},
    {"url": "https://www.scmp.com/rss/91/feed", "source": "SCMP", "org": "scmp", "standing": "report"},
    {"url": "https://en.yna.co.kr/RSS/news.xml", "source": "Yonhap", "org": "yonhap", "standing": "report"},
    {"url": "https://www.japantimes.co.jp/feed/", "source": "The Japan Times", "org": "japantimes", "standing": "report"},
    {"url": "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6311", "source": "CNA", "org": "cna", "standing": "report"},
    {"url": "https://www.straitstimes.com/news/world/rss.xml", "source": "The Straits Times", "org": "straits", "standing": "report"},
    {"url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada", "source": "El Pais", "org": "elpais", "standing": "report"},
    {"url": "https://www.lemonde.fr/en/international/rss_full.xml", "source": "Le Monde", "org": "lemonde", "standing": "report"},
    {"url": "https://www.spiegel.de/international/index.rss", "source": "Der Spiegel", "org": "spiegel", "standing": "report"},
    {"url": "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms", "source": "Times of India", "org": "toi", "standing": "report"},
    {"url": "https://www.africanews.com/feed/rss", "source": "Africanews", "org": "africanews", "standing": "report"},
    {"url": "https://www.theafricareport.com/feed/", "source": "The Africa Report", "org": "africa-report", "standing": "report"},
    {"url": "https://www.themoscowtimes.com/rss/news", "source": "The Moscow Times", "org": "moscow-times", "standing": "report"},
    {"url": "https://meduza.io/rss/en/all", "source": "Meduza", "org": "meduza", "standing": "report"},
    {"url": "https://balkaninsight.com/feed/", "source": "BIRN", "org": "birn", "standing": "report"},
    {"url": "https://www.middleeasteye.net/rss", "source": "Middle East Eye", "org": "mee", "standing": "report"},
    {"url": "https://iranwire.com/en/feed/", "source": "IranWire", "org": "iranwire", "standing": "report"},
    {"url": "https://www.ft.com/world?format=rss", "source": "Financial Times", "org": "ft", "standing": "report"},
    {"url": "https://www.ft.com/markets?format=rss", "source": "FT Markets", "org": "ft-markets", "standing": "report"},
    {"url": "https://feeds.bloomberg.com/politics/news.rss", "source": "Bloomberg", "org": "bloomberg", "standing": "report"},
    {"url": "https://feeds.bloomberg.com/markets/news.rss", "source": "Bloomberg Markets", "org": "bloomberg-markets", "standing": "report"},
    {"url": "http://feeds.bbci.co.uk/news/business/rss.xml", "source": "BBC Business", "org": "bbc-business", "standing": "report"},
    {"url": "https://www.theguardian.com/business/rss", "source": "Guardian Business", "org": "guardian-business", "standing": "report"},
    {"url": "https://rss.dw.com/rdf/rss-en-bus", "source": "DW Business", "org": "dw-business", "standing": "report"},
    {"url": "https://feeds.npr.org/1006/rss.xml", "source": "NPR Business", "org": "npr-business", "standing": "report"},
    {"url": "https://feeds.marketwatch.com/marketwatch/topstories/", "source": "MarketWatch", "org": "marketwatch", "standing": "report"},
    {"url": "https://oilprice.com/rss/main", "source": "OilPrice", "org": "oilprice", "standing": "report"},
    {"url": "https://www.bellingcat.com/feed/", "source": "Bellingcat", "org": "bellingcat", "standing": "report", "lookback_hours": 168},
    {"url": "https://www.occrp.org/en/feed", "source": "OCCRP", "org": "occrp", "standing": "report", "lookback_hours": 168},
    {"url": "https://www.icij.org/feed/", "source": "ICIJ", "org": "icij", "standing": "report", "lookback_hours": 168},
    {"url": "https://syriadirect.org/feed/", "source": "Syria Direct", "org": "syria-direct", "standing": "report", "lookback_hours": 168},
    {"url": "https://sudanwarmonitor.com/feed/", "source": "Sudan War Monitor", "org": "sudan-war-monitor", "standing": "report", "lookback_hours": 168},
    {"url": "https://airwars.org/feed/", "source": "Airwars", "org": "airwars", "standing": "report", "lookback_hours": 168},
    {"url": "https://www.hrw.org/rss/news", "source": "Human Rights Watch", "org": "hrw", "standing": "report", "lookback_hours": 168},
    {"url": "https://www.amnesty.org/en/latest/news/feed/", "source": "Amnesty International", "org": "amnesty", "standing": "report", "lookback_hours": 168},
    {"url": "https://www.propublica.org/feeds/propublica/main", "source": "ProPublica", "org": "propublica", "standing": "report", "lookback_hours": 168},
    {"url": "https://news.un.org/feed/subscribe/en/news/all/rss.xml", "source": "UN News", "org": "un", "standing": "statement"},
    {"url": "https://news.un.org/feed/subscribe/en/news/topic/peace-and-security/feed/rss.xml", "source": "UN Peace and Security", "org": "un", "standing": "statement"},
    {"url": "https://www.iaea.org/feeds/topnews", "source": "IAEA", "org": "iaea", "standing": "statement"},
    {"url": "https://www.who.int/rss-feeds/news-english.xml", "source": "WHO", "org": "who", "standing": "statement"},
    {"url": "https://tass.com/rss/v2.xml", "source": "TASS", "org": "tass", "standing": "statement"},
    {"url": "https://en.irna.ir/rss", "source": "IRNA", "org": "irna", "standing": "statement"},
    {"url": "https://www.aa.com.tr/en/rss/default?cat=world", "source": "Anadolu", "org": "anadolu", "standing": "statement"},
    {"url": "https://www.nhc.noaa.gov/index-at.xml", "source": "NHC Atlantic", "org": "nhc", "standing": "record"},
    {"url": "https://www.nhc.noaa.gov/index-ep.xml", "source": "NHC Pacific", "org": "nhc", "standing": "record"},
]

SENSOR_ORGS = {"usgs", "eonet", "gdacs", "nhc"}
SATELLITE_ORGS = {"copernicus-ems"}

METHOD = (
    "This brief states only what a source or an instrument published. "
    "Priority topics are war, economy, persecution, and stability. "
    "Environment and natural-hazard sensor records are kept, but ranked below those topics "
    f"and capped at {MAX_ENVIRONMENT_EVENTS} items. "
    "A report is included when at least two independent news or OSINT outlets published it, "
    "or when a measurement institution recorded it. "
    "State and government outlets are quoted as statements and are not counted as confirmation. "
    "A Sentinel-2 scene, when listed, is a file covering that location. The image is not interpreted. "
    "A Copernicus Emergency Management Service entry is included only when that service published map products. "
    "USGS earthquakes are included at magnitude 5.5 or higher. "
    "GDACS forest-fire notifications are omitted. Other GDACS bulletins from the last 72 hours are included. "
    "No forecast, threat rating, or recommendation is added."
)

IMAGERY_NOTE = (
    "A Sentinel-2 scene covering this location is on file. The image was not interpreted, "
    "so the scene does not confirm or deny the report."
)

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
    "georss": "http://www.georss.org/georss",
}


def utc_now():
    return datetime.now(timezone.utc)


def parse_dt(value):
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    iso = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def fetch_bytes(url, timeout=12):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, application/json, */*"})
    with urlopen(req, timeout=timeout) as response:
        return response.read()


def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    return re.sub(r"\s+", " ", text).strip()


def event_class(text):
    low = (text or "").lower()
    for name, terms in CLASS_TERMS:
        for term in terms:
            if re.search(r"\b" + re.escape(term) + r"\b", low):
                return name
    return "other"


def normalize_place_text(text):
    text = re.sub(r"\bU\.?S\.?A?\.?\b", "United States", text or "")
    text = re.sub(r"\bU\.?K\.?\b", "United Kingdom", text)
    return text


def find_places(text):
    padded = " " + re.sub(r"[^a-z0-9]+", " ", normalize_place_text(text).lower()) + " "
    occupied = [False] * len(padded)
    found = []
    for name in sorted(GAZETTEER, key=len, reverse=True):
        needle = " " + name + " "
        start = 0
        while True:
            index = padded.find(needle, start)
            if index < 0:
                break
            end = index + len(needle)
            if not any(occupied[index:end]):
                for pos in range(index, end):
                    occupied[pos] = True
                found.append(name)
            start = index + len(needle)
    return found


def specific_places(text):
    return {place for place in find_places(text) if place not in LARGE_PLACES}


def haversine_km(lat1, lon1, lat2, lon2):
    from math import asin, cos, radians, sin, sqrt
    rlat1, rlon1, rlat2, rlon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


def article_point(article):
    if article.get("lat") is not None and article.get("lon") is not None:
        return float(article["lat"]), float(article["lon"])
    places = specific_places(article.get("title", "") + " " + article.get("summary", ""))
    if not places:
        return None
    name = max(places, key=len)
    return GAZETTEER[name]


def tokens(text):
    words = re.findall(r"[a-z0-9]{4,}", (text or "").lower())
    return {word for word in words if word not in STOPWORDS and word not in GAZETTEER}


def jaccard(left, right):
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def article_class(article):
    if article.get("standing") == "record" and article.get("event_class") not in (None, "", "other"):
        return article["event_class"]
    return event_class(article.get("title", "") + " " + article.get("summary", ""))


def storm_names(text):
    found = set()
    for match in re.finditer(
        r"\b(?:hurricane|typhoon|cyclone|tropical storm|tropical depression)\s+([A-Za-z]{4,})",
        text or "",
        re.I,
    ):
        name = match.group(1).lower()
        if name not in STOPWORDS:
            found.add(name)
    return found


def include_nhc_title(title):
    if re.search(r"no tropical cyclones|tropical weather outlook", title or "", re.I):
        return False
    if not re.search(r"\b(?:Hurricane|Typhoon|Tropical Storm|Tropical Depression)\s+[A-Z][a-z]{3,}", title or ""):
        return False
    # Forecast discussions, graphics, and probability tables are forecasts.
    # The public advisory is the bulletin kept on the record.
    if re.search(r"graphics|forecast|probabilities|discussion|summary for", title or "", re.I):
        return False
    return True


def related_text(article):
    # Record summaries repeat the same instrument sentence. Compare titles,
    # or every earthquake bulletin matches every other earthquake bulletin.
    if article.get("standing") == "record":
        return article.get("title") or ""
    return (article.get("title") or "") + " " + (article.get("summary") or "")


def related(left, right):
    left_text = related_text(left)
    right_text = related_text(right)
    if storm_names(left_text) & storm_names(right_text):
        return True
    left_class = article_class(left)
    right_class = article_class(right)
    same_class = left_class == right_class and left_class != "other"
    left_specific = specific_places(left_text)
    right_specific = specific_places(right_text)
    share_specific = bool(left_specific & right_specific)
    left_point = article_point(left)
    right_point = article_point(right)
    too_far = False
    if left_point and right_point and same_class:
        limit = DISTANCE_KM.get(left_class, 100)
        too_far = haversine_km(*left_point, *right_point) > limit
    both_records = left.get("standing") == "record" and right.get("standing") == "record"
    if both_records:
        # Bulletin titles share boilerplate ("Green flood alert in").
        # Two records match only when the place or the measurement agrees.
        if same_class and share_specific and not too_far:
            return True
        if (
            same_class
            and left_point and right_point and not too_far
            and not (left_specific and right_specific and not share_specific)
        ):
            return True
        return False
    # Same or near-same headline from two outlets is enough even when
    # summaries diverge (common for wire copy and rights-group releases).
    title_score = jaccard(tokens(left.get("title") or ""), tokens(right.get("title") or ""))
    if title_score >= 0.7:
        return True
    score = jaccard(tokens(left_text), tokens(right_text))
    if score >= 0.45:
        return True
    if same_class and share_specific and not too_far:
        return True
    if share_specific and score >= 0.18 and not too_far:
        return True
    return False


def cluster_articles(articles):
    clusters = []
    used = set()
    for index, article in enumerate(articles):
        if index in used:
            continue
        group = [article]
        used.add(index)
        for other_index, other in enumerate(articles):
            if other_index in used:
                continue
            if related(article, other):
                group.append(other)
                used.add(other_index)
        clusters.append(group)
    return clusters


def _local(tag):
    return tag.split("}", 1)[-1]


def parse_feed_items(xml_bytes):
    if not xml_bytes:
        return []
    if xml_bytes.startswith(b"\xef\xbb\xbf"):
        xml_bytes = xml_bytes[3:]
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    items = []
    nodes = (
        list(root.iter("item"))
        + list(root.iter("{http://www.w3.org/2005/Atom}entry"))
        + list(root.iter("{http://purl.org/rss/1.0/}item"))
    )
    for node in nodes:
        title = ""
        link = ""
        summary = ""
        published = ""
        lat = None
        lon = None
        for child in list(node):
            name = _local(child.tag)
            value = (child.text or "").strip()
            if name == "title" and value:
                title = strip_html(value)
            elif name == "description" or name == "summary" or name == "encoded":
                if value and len(value) > len(summary):
                    summary = strip_html(value)
            elif name == "link":
                link = child.attrib.get("href") or value or link
            elif name in ("pubDate", "published", "updated", "date"):
                published = published or value
            elif name == "lat" and value:
                lat = _float_or_none(value)
            elif name in ("long", "lon") and value:
                lon = _float_or_none(value)
            elif name == "point" and value:
                parts = value.split()
                if len(parts) >= 2:
                    lat = _float_or_none(parts[0])
                    lon = _float_or_none(parts[1])
        if title and len(title) >= 8:
            items.append({
                "title": title,
                "summary": summary[:500],
                "url": link,
                "published_raw": published,
                "lat": lat,
                "lon": lon,
            })
    return items


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_feed(feed, now=None):
    now = now or utc_now()
    cutoff = now - timedelta(hours=feed.get("lookback_hours", NEWS_LOOKBACK_HOURS))
    try:
        payload = fetch_bytes(feed["url"], timeout=12)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return [], str(exc.__class__.__name__)
    articles = []
    for item in parse_feed_items(payload):
        published = parse_dt(item["published_raw"])
        if published is None or published < cutoff:
            continue
        title = item["title"]
        if "nhc.noaa.gov" in feed["url"] and not include_nhc_title(title):
            continue
        if "nhc.noaa.gov" in feed["url"]:
            item["summary"] = ""
        text = title + " " + item["summary"]
        observation = None
        if feed["standing"] == "record":
            observation = f"{feed['source']} published: {title}."
            if item["summary"] and "nhc.noaa.gov" not in feed["url"]:
                observation += " " + item["summary"]
        articles.append({
            "title": title,
            "summary": item["summary"],
            "url": item["url"],
            "source": feed["source"],
            "org": feed["org"],
            "standing": feed["standing"],
            "published": published.isoformat(),
            "event_class": event_class(text),
            "lat": item["lat"],
            "lon": item["lon"],
            "observation": observation,
        })
    articles.sort(key=lambda article: article["published"], reverse=True)
    return articles[:MAX_PER_FEED], None


def _iso_from_millis(millis):
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).isoformat()


def fetch_usgs(now=None):
    now = now or utc_now()
    start = (now - timedelta(hours=SENSOR_LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%S")
    url = (
        "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson"
        f"&starttime={start}&minmagnitude=5.5&orderby=time&limit=30"
    )
    try:
        payload = json.loads(fetch_bytes(url, timeout=20))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return [], str(exc.__class__.__name__)
    articles = []
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
        mag = props.get("mag")
        place = props.get("place") or ""
        when = _iso_from_millis(props["time"]) if props.get("time") else ""
        title = props.get("title") or f"M {mag} {place}"
        status = props.get("status") or ""
        observation = (
            f"USGS recorded a magnitude {mag} earthquake, {place}, at {when}. "
            f"Review status on the USGS record: {status}."
        )
        articles.append({
            "title": title,
            "summary": observation,
            "url": props.get("url") or "",
            "source": "USGS",
            "org": "usgs",
            "standing": "record",
            "published": when,
            "event_class": "earthquake",
            "lat": coords[1],
            "lon": coords[0],
            "observation": observation,
        })
    return articles, None


def fetch_eonet(now=None):
    now = now or utc_now()
    cutoff = now - timedelta(hours=SENSOR_LOOKBACK_HOURS)
    url = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=80"
    try:
        payload = json.loads(fetch_bytes(url, timeout=20))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return [], str(exc.__class__.__name__)
    class_by_category = {
        "severeStorms": "storm",
        "wildfires": "fire",
        "volcanoes": "volcano",
        "earthquakes": "earthquake",
        "floods": "flood",
        "landslides": "landslide",
    }
    articles = []
    for event in payload.get("events") or []:
        categories = event.get("categories") or []
        category_id = categories[0]["id"] if categories else ""
        event_type = class_by_category.get(category_id)
        if not event_type:
            continue
        geometry = event.get("geometry") or []
        latest = geometry[-1] if geometry else {}
        when = parse_dt(latest.get("date") or "")
        if when is None or when < cutoff:
            continue
        coords = latest.get("coordinates") or [None, None]
        magnitude = latest.get("magnitudeValue")
        unit = latest.get("magnitudeUnit") or ""
        magnitude_text = ""
        if magnitude is not None:
            magnitude_text = f" Latest recorded value: {magnitude} {unit}."
        title = event.get("title") or "EONET event"
        observation = (
            f"NASA EONET lists {title} as an open {categories[0].get('title', event_type)} event. "
            f"Latest position on that record: {coords[1]}, {coords[0]} at {when.isoformat()}."
            f"{magnitude_text}"
        )
        articles.append({
            "title": title,
            "summary": observation,
            "url": event.get("link") or "https://eonet.gsfc.nasa.gov/",
            "source": "NASA EONET",
            "org": "eonet",
            "standing": "record",
            "published": when.isoformat(),
            "event_class": event_type,
            "lat": coords[1],
            "lon": coords[0],
            "observation": observation,
        })
    return articles[:25], None


def fetch_gdacs(now=None):
    now = now or utc_now()
    cutoff = now - timedelta(hours=SENSOR_LOOKBACK_HOURS)
    try:
        payload = fetch_bytes("https://www.gdacs.org/xml/rss.xml", timeout=20)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return [], str(exc.__class__.__name__)
    articles = []
    class_by_word = {
        "earthquake": "earthquake",
        "flood": "flood",
        "cyclone": "storm",
        "tropical": "storm",
        "volcano": "volcano",
        "wildfire": "fire",
        "drought": "other",
    }
    for item in parse_feed_items(payload):
        published = parse_dt(item["published_raw"])
        if published is None or published < cutoff:
            continue
        title = item["title"]
        kind = "other"
        low = title.lower()
        for word, mapped in class_by_word.items():
            if word in low:
                kind = mapped
                break
        if kind == "other" or "forest fire notification" in low:
            continue
        observation = f"GDACS published: {title}"
        if item["summary"]:
            observation += " " + item["summary"]
        articles.append({
            "title": title,
            "summary": item["summary"],
            "url": item["url"],
            "source": "GDACS",
            "org": "gdacs",
            "standing": "record",
            "published": published.isoformat(),
            "event_class": kind,
            "lat": item["lat"],
            "lon": item["lon"],
            "observation": observation,
        })
    articles.sort(key=lambda article: article["published"], reverse=True)
    return articles[:20], None


def _point_wkt(value):
    if not value:
        return None, None
    match = re.search(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", value)
    if not match:
        return None, None
    return _float_or_none(match.group(2)), _float_or_none(match.group(1))


def fetch_copernicus(now=None):
    now = now or utc_now()
    cutoff = now - timedelta(hours=EMS_LOOKBACK_HOURS)
    url = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations-info/?limit=40"
    try:
        payload = json.loads(fetch_bytes(url, timeout=20))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return [], str(exc.__class__.__name__)
    category_map = {
        "earthquake": "earthquake",
        "flood": "flood",
        "wildfire": "fire",
        "fire": "fire",
        "storm": "storm",
        "cyclone": "storm",
        "volcano": "volcano",
        "landslide": "landslide",
    }
    articles = []
    for row in payload.get("results") or []:
        when = parse_dt(row.get("eventTime") or "") or parse_dt(row.get("activationTime") or "")
        if when is None or when < cutoff:
            continue
        if int(row.get("n_products") or 0) < 1:
            continue
        category = (row.get("category") or "").lower()
        kind = "other"
        for word, mapped in category_map.items():
            if word in category:
                kind = mapped
                break
        lat, lon = _point_wkt(row.get("centroid") or "")
        code = row.get("code") or ""
        name = row.get("name") or code
        countries = ", ".join(row.get("countries") or [])
        products = int(row.get("n_products") or 0)
        observation = (
            f"Copernicus Emergency Management Service activation {code} ({name}"
            + (f", {countries}" if countries else "")
            + f") lists {products} published map products. "
            f"Event time on that record: {when.isoformat()}."
        )
        articles.append({
            "title": name,
            "summary": observation,
            "url": f"https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code={code}",
            "source": "Copernicus EMS",
            "org": "copernicus-ems",
            "standing": "record",
            "published": when.isoformat(),
            "event_class": kind,
            "lat": lat,
            "lon": lon,
            "observation": observation,
            "map_products": products,
            "activation_code": code,
        })
    return articles, None


def fetch_acled(now=None):
    now = now or utc_now()
    key = os.environ.get("ACLED_API_KEY")
    email = os.environ.get("ACLED_EMAIL")
    if not key or not email:
        return [], "not_configured"
    start = (now - timedelta(hours=SENSOR_LOOKBACK_HOURS)).date().isoformat()
    end = now.date().isoformat()
    url = (
        "https://api.acleddata.com/acled/read?format=json&limit=40"
        f"&key={key}&email={email}&event_date={start}|{end}&event_date_where=BETWEEN"
        "&fields=event_date|event_type|country|location|fatalities|notes|source"
    )
    try:
        payload = json.loads(fetch_bytes(url, timeout=20))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return [], str(exc.__class__.__name__)
    articles = []
    for row in payload.get("data") or []:
        fatalities = row.get("fatalities")
        title = (
            f"ACLED recorded {row.get('event_type') or 'an event'} in "
            f"{row.get('location') or ''}, {row.get('country') or ''}. "
            f"Fatalities on the ACLED record: {fatalities}."
        )
        articles.append({
            "title": title,
            "summary": (row.get("notes") or "")[:400],
            "url": "https://acleddata.com/",
            "source": "ACLED",
            "org": "acled",
            "standing": "record",
            "published": (row.get("event_date") or "") + "T00:00:00+00:00",
            "event_class": "other",
            "lat": None,
            "lon": None,
            "observation": title,
        })
    return articles, None


def fetch_firms_count(lat, lon):
    key = os.environ.get("NASA_FIRMS_MAP_KEY")
    if not key:
        return None, "not_configured"
    west, south, east, north = lon - 0.4, lat - 0.4, lon + 0.4, lat + 0.4
    url = (
        f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/"
        f"{west},{south},{east},{north}/2"
    )
    try:
        payload = fetch_bytes(url, timeout=20).decode("utf-8", "replace")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return None, str(exc.__class__.__name__)
    lines = [line for line in payload.splitlines() if line.strip()]
    count = max(len(lines) - 1, 0)
    return count, None


def lookup_sentinel(lat, lon, now=None):
    now = now or utc_now()
    start = (now - timedelta(days=10)).strftime("%Y-%m-%dT00:00:00Z")
    end = now.strftime("%Y-%m-%dT23:59:59Z")
    body = json.dumps({
        "collections": ["sentinel-2-l2a"],
        "intersects": {"type": "Point", "coordinates": [lon, lat]},
        "datetime": f"{start}/{end}",
        "limit": 1,
        "query": {"eo:cloud_cover": {"lt": 40}},
    }).encode()
    req = Request(
        "https://planetarycomputer.microsoft.com/api/stac/v1/search",
        data=body,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as response:
            payload = json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return None, str(exc.__class__.__name__)
    features = payload.get("features") or []
    if not features:
        return None, None
    feature = features[0]
    cloud = (feature.get("properties") or {}).get("eo:cloud_cover")
    acquired = (feature.get("properties") or {}).get("datetime")
    return {
        "collection": "sentinel-2-l2a",
        "scene_id": feature.get("id"),
        "acquired": acquired,
        "cloud_cover_pct": cloud,
        "note": IMAGERY_NOTE,
    }, None


def _parse_number(raw):
    return float(str(raw).replace(",", ""))


FIGURE_PATTERNS = (
    ("killed", re.compile(r"\b(\d{1,3}(?:,\d{3})*|\d+)\s+(?:people\s+)?(?:were\s+|was\s+)?(?:killed|dead)\b", re.I)),
    ("killed", re.compile(r"\b(?:death toll(?: of)?|fatalities)\s*(?:of|:)?\s*(\d{1,3}(?:,\d{3})*|\d+)\b", re.I)),
    ("injured", re.compile(r"\b(\d{1,3}(?:,\d{3})*|\d+)\s+(?:people\s+)?(?:were\s+)?(?:injured|wounded)\b", re.I)),
    ("magnitude", re.compile(r"\bmagnitude\s+(\d+(?:\.\d+)?)(?!\d)", re.I)),
)


def keep_coordinates(title, lat, lon):
    """Drop coordinates that disagree with a place named in the title."""
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None
    places = specific_places(title or "")
    if places:
        name = max(places, key=len)
        place_lat, place_lon = GAZETTEER[name]
        if haversine_km(lat, lon, place_lat, place_lon) > 700:
            return None, None
    return lat, lon


def figures_in(article):
    text = article.get("title", "") + " " + article.get("summary", "")
    found = []
    for label, pattern in FIGURE_PATTERNS:
        for match in pattern.finditer(text):
            value = _parse_number(match.group(1))
            if label == "magnitude":
                value = round(value, 1)
            else:
                value = int(value)
            found.append({"source": article["source"], "label": label, "value": value})
    return found


def conflicting_figures(articles):
    grouped = {}
    for article in articles:
        for figure in figures_in(article):
            grouped.setdefault(figure["label"], []).append(figure)
    conflicts = []
    for label, rows in grouped.items():
        by_source = {}
        for row in rows:
            by_source.setdefault(row["source"], set()).add(row["value"])
        values = set()
        for source_values in by_source.values():
            values |= source_values
        if len(by_source) >= 2 and len(values) >= 2:
            for source, source_values in sorted(by_source.items()):
                for value in sorted(source_values):
                    conflicts.append({"source": source, "label": label, "value": value})
    return conflicts


def choose_headline(articles):
    reports = [article for article in articles if article["standing"] == "report"] or articles
    preferred = [article for article in reports if re.search(r"public advisory", article["title"], re.I)]
    reports = preferred or reports
    def score(article):
        title_tokens = tokens(article["title"])
        shared = 0
        for other in reports:
            if other is article:
                continue
            shared += len(title_tokens & tokens(other["title"]))
        return (shared, -len(article["title"]))
    return max(reports, key=score)["title"]


def unique_sources(articles, standing):
    seen = []
    for article in articles:
        if article["standing"] != standing:
            continue
        if article["source"] not in seen:
            seen.append(article["source"])
    return seen


def instrument_confirms(report_text, instrument):
    report_class = event_class(report_text)
    if report_class == "other" or report_class != instrument.get("event_class"):
        return False
    report_specific = specific_places(report_text)
    instrument_text = instrument.get("title", "") + " " + (instrument.get("observation") or "")
    instrument_specific = specific_places(instrument_text)
    if report_specific and instrument_specific and (report_specific & instrument_specific):
        return True
    report_point = None
    places = specific_places(report_text)
    if len(places) >= 1:
        report_point = GAZETTEER[max(places, key=len)]
    if (
        report_point
        and instrument.get("lat") is not None
        and instrument.get("lon") is not None
    ):
        limit = DISTANCE_KM.get(report_class, 100)
        distance = haversine_km(report_point[0], report_point[1], float(instrument["lat"]), float(instrument["lon"]))
        if distance <= limit and not (report_specific and instrument_specific and not (report_specific & instrument_specific)):
            return True
    return False


def _outlets(articles):
    rows = []
    seen = set()
    for article in articles:
        key = (article["source"], article.get("url") or article["title"])
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "name": article["source"],
            "url": article.get("url") or "",
            "published": article.get("published") or "",
            "standing": article["standing"],
            "org": article["org"],
        })
    return rows


def _event_id(articles):
    basis = "|".join(sorted(article.get("url") or article["title"] for article in articles))
    return hashlib.sha256(basis.encode()).hexdigest()[:12]


def _paragraphs(cluster, confirmed, nearby, conflicts):
    reports = unique_sources(cluster, "report")
    statements = unique_sources(cluster, "statement")
    records = [article for article in cluster if article["standing"] == "record" and article.get("observation")]
    paragraphs = []
    if reports:
        paragraphs.append(choose_headline(cluster))
        paragraphs.append(
            f"Reported by {len(reports)} independent outlets: {', '.join(reports)}."
        )
    elif records:
        paragraphs.append(records[0]["observation"])
        extra = [article["source"] for article in records[1:]]
        if extra:
            paragraphs.append("Also recorded by " + ", ".join(dict.fromkeys(extra)) + ".")
    else:
        paragraphs.append(choose_headline(cluster))
    if statements and reports:
        paragraphs.append(
            "Also published by " + ", ".join(statements) + ". Those outlets are not counted as confirmation."
        )
    elif statements and not reports:
        paragraphs.append(
            "Published by " + ", ".join(statements) + ". This is the text of that publication, not a separate confirmation."
        )
    if conflicts:
        bits = [f"{row['source']} published {row['value']} {row['label']}" for row in conflicts]
        paragraphs.append("The published figures differ: " + "; ".join(bits) + ".")
    seen_obs = set()
    for instrument in confirmed:
        obs = instrument.get("observation")
        if obs and obs not in seen_obs and obs not in paragraphs:
            seen_obs.add(obs)
            paragraphs.append(obs)
    for instrument in nearby:
        obs = instrument.get("observation")
        if not obs or obs in seen_obs:
            continue
        seen_obs.add(obs)
        paragraphs.append(obs + " This instrument recorded a different event type, so it is not confirmation of the report.")
    return paragraphs


def _labels(cluster, promoting, conflicts):
    reports = unique_sources(cluster, "report")
    labels = []
    if any(article.get("org") in SATELLITE_ORGS for article in promoting):
        labels.append("satellite-mapped")
    if any(article.get("org") in SENSOR_ORGS for article in promoting):
        labels.append("sensor-confirmed")
    if any(article.get("org") not in SENSOR_ORGS | SATELLITE_ORGS for article in promoting):
        labels.append("dataset-record")
    if len(reports) >= 2:
        labels.append("multi-source")
    if conflicts:
        labels.append("figures-differ")
    if not labels and len(reports) == 1:
        labels.append("single-outlet")
    if not labels and unique_sources(cluster, "statement"):
        labels.append("statement")
    return labels


def _text_has_term(text, terms):
    """Match whole terms only (word boundaries). Avoids 'war' in 'warning'."""
    low = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "
    for term in terms:
        needle = f" {term} "
        if needle in low:
            return True
        # Allow simple plural/suffix when the term is a single word.
        if " " not in term and re.search(rf"\b{re.escape(term)}s?\b", low):
            return True
    return False


def event_topic(event):
    """Assign one priority topic. Economy market language is checked before war
    so oil, inflation, and defence-budget stories are not misfiled as conflict."""
    text = (event.get("headline") or "") + " " + " ".join(event.get("paragraphs") or [])
    classes = [
        (instrument.get("event_class") or "")
        for instrument in event.get("instruments") or []
        if instrument.get("event_class") not in (None, "", "other")
    ]
    is_hazard = any(
        kind in ("earthquake", "volcano", "storm", "flood", "fire", "landslide")
        for kind in classes
    ) or _text_has_term(
        text,
        ("earthquake", "magnitude", "tropical storm", "hurricane", "typhoon", "flood alert", "wildfire", "volcano"),
    )

    if _text_has_term(text, ECONOMY_TERMS):
        return "economics"
    if _text_has_term(text, WAR_TERMS):
        return "conflict-war"
    if _text_has_term(text, PERSECUTION_TERMS):
        return "persecution"
    if _text_has_term(text, STABILITY_TERMS):
        return "stability"
    if _text_has_term(text, ("election", "parliament", "president", "minister", "court", "arrest", "protest", "vote", "cabinet")):
        return "politics"
    if is_hazard:
        return "environment"
    return "politics"


def _is_environment_event(event):
    return event_topic(event) == "environment"


def _sort_key(event):
    labels = event["labels"]
    topic = event.get("topic") or event_topic(event)
    rank = TOPIC_PRIORITY.get(topic, TOPIC_PRIORITY["other"])
    if "multi-source" in labels:
        rank += 80
    if "sensor-confirmed" in labels or "satellite-mapped" in labels:
        # Sensor confirmation still matters, but not more than topic priority.
        rank += 25 if topic != "environment" else 10
    if "dataset-record" in labels:
        rank += 15
    if "figures-differ" in labels:
        rank += 5
    rank += 12 * event.get("independent_outlet_count", 0)
    return (rank, event.get("published") or "")


def _card_category(event):
    return event.get("topic") or event_topic(event)


def prioritize_events(events):
    """Keep priority topics first; cap environment-only hazard records."""
    for event in events:
        event["topic"] = event_topic(event)
    priority = [event for event in events if not _is_environment_event(event)]
    environment = [event for event in events if _is_environment_event(event)]
    priority.sort(key=_sort_key, reverse=True)
    environment.sort(key=_sort_key, reverse=True)
    environment = environment[:MAX_ENVIRONMENT_EVENTS]
    combined = priority + environment
    truncated_environment = len([event for event in events if _is_environment_event(event)]) > MAX_ENVIRONMENT_EVENTS
    return combined[:MAX_EVENTS], truncated_environment


def prioritize_singles(singles):
    """Sort singles by priority, but reserve floor slots for economy and peers."""
    for event in singles:
        event["topic"] = event_topic(event)
    singles = sorted(singles, key=_sort_key, reverse=True)
    kept = []
    used = set()

    def _add(event):
        marker = id(event)
        if marker in used or len(kept) >= MAX_SINGLE:
            return
        kept.append(event)
        used.add(marker)

    for topic, floor in SINGLE_TOPIC_FLOOR.items():
        for event in [row for row in singles if row.get("topic") == topic][:floor]:
            _add(event)
    for event in singles:
        _add(event)
    return kept[:MAX_SINGLE]


def _story_place_text(event):
    """Headline plus fact lines, excluding outlet-attribution boilerplate."""
    parts = [event.get("headline") or ""]
    for paragraph in event.get("paragraphs") or []:
        low = (paragraph or "").lower()
        if low.startswith("reported by ") or low.startswith("also recorded by "):
            continue
        if "independent outlets:" in low:
            continue
        parts.append(paragraph)
    return " ".join(parts)


def _card_region(event):
    text = _story_place_text(event)
    places = find_places(text)
    region_for = {
        "middle-east": [
            "iran", "iraq", "syria", "israel", "gaza", "lebanon", "yemen", "saudi arabia",
            "jordan", "qatar", "united arab emirates", "bahrain", "oman", "palestine",
            "tehran", "baghdad", "damascus", "beirut", "sanaa", "rafah", "jerusalem", "tel aviv",
        ],
        "europe": [
            "ukraine", "kyiv", "kharkiv", "odesa", "germany", "france", "united kingdom",
            "poland", "spain", "italy", "romania", "greece", "belgium", "netherlands",
            "london", "paris", "berlin", "brussels", "madrid", "rome", "vienna", "geneva",
        ],
        "africa": [
            "sudan", "darfur", "el fasher", "khartoum", "ethiopia", "kenya", "nigeria",
            "mali", "niger", "somalia", "south africa", "mozambique", "chad", "ghana",
            "addis ababa", "nairobi", "lagos", "abuja", "bamako", "mogadishu",
        ],
        "asia-pacific": [
            "china", "taiwan", "japan", "south korea", "north korea", "philippines",
            "indonesia", "malaysia", "vietnam", "thailand", "australia", "new zealand",
            "beijing", "shanghai", "hong kong", "tokyo", "seoul", "pyongyang", "taipei",
            "manila", "jakarta", "vanuatu", "port-olry", "port vila",
        ],
        "americas": [
            "united states", "canada", "mexico", "brazil", "colombia", "venezuela",
            "argentina", "peru", "chile", "panama", "cuba", "haiti",
            "los angeles", "san francisco", "california", "florida", "texas", "hawaii", "alaska",
            "mexico city", "brasilia", "sao paulo", "bogota", "caracas", "lima",
        ],
        "russia-fsu": [
            "russia", "moscow", "belarus", "minsk", "kazakhstan", "uzbekistan",
            "georgia", "armenia", "azerbaijan", "kyrgyzstan", "tajikistan", "turkmenistan",
            "st petersburg",
        ],
        "south-asia": [
            "india", "pakistan", "bangladesh", "sri lanka", "afghanistan", "nepal", "myanmar",
            "new delhi", "mumbai", "islamabad", "karachi", "kabul", "dhaka",
        ],
    }
    for region, names in region_for.items():
        if any(place in places for place in names):
            return region
    return "global"


def _card_location(event):
    text = _story_place_text(event)
    places = find_places(text)
    if not places:
        return ""
    preferred = [place for place in places if place not in LARGE_PLACES] or places
    name = max(preferred, key=len)
    return name.title()


def _card_badge(labels):
    if "sensor-confirmed" in labels:
        return "SENSOR RECORD", "b-verified"
    if "satellite-mapped" in labels:
        return "SATELLITE MAP", "b-corroborated"
    if "multi-source" in labels:
        return "MULTI-SOURCE", "b-corroborated"
    if "dataset-record" in labels:
        return "DATASET", "b-single"
    if "single-outlet" in labels:
        return "ONE OUTLET", "b-single"
    if "statement" in labels:
        return "STATEMENT", "b-unverified"
    return "RECORDED", "b-single"


def event_to_story_card(event, section="events"):
    """Shape a fact event as a story card. No analysis fields."""
    labels = list(event.get("labels") or [])
    paragraphs = list(event.get("paragraphs") or [])
    outlets = event.get("outlets") or []
    sources = list(dict.fromkeys(outlet["name"] for outlet in outlets if outlet.get("name")))
    badge, badge_class = _card_badge(labels)
    summary = paragraphs[0] if paragraphs else (event.get("headline") or "")
    known = paragraphs[1:] if len(paragraphs) > 1 else []
    instruments = [
        {
            "source": instrument.get("source"),
            "observation": instrument.get("observation"),
            "url": instrument.get("url") or "",
            "confirms": bool(instrument.get("confirms")),
        }
        for instrument in event.get("instruments") or []
        if instrument.get("observation")
    ]
    imagery = event.get("imagery")
    card = {
        "id": event.get("id"),
        "headline": event.get("headline") or "",
        "summary": summary,
        "what_is_known": known,
        "paragraphs": paragraphs,
        "labels": labels,
        "section": section,
        "category": _card_category(event),
        "region": _card_region(event),
        "location": _card_location(event),
        "published": event.get("published") or "",
        "updated": event.get("published") or "",
        "sources": sources,
        "source_count": len(sources),
        "article_urls": [outlet.get("url") for outlet in outlets if outlet.get("url")],
        "outlets": outlets,
        "instruments": instruments,
        "figures": event.get("figures") or [],
        "lat": event.get("lat"),
        "lon": event.get("lon"),
        "imagery": imagery,
        "confidence_badge": badge,
        "confidence_badge_class": badge_class,
        "confidence": "high" if badge in ("SENSOR RECORD", "SATELLITE MAP", "MULTI-SOURCE") else "medium" if badge != "STATEMENT" else "low",
        "confidence_reason": "Labels: " + ", ".join(labels) if labels else "Listed in the fact brief.",
        # Keep analysis fields empty so older renderers cannot invent a narrative.
        "who_benefits": None,
        "significance": "",
        "contested_claim": "",
        "paragraph_2_connections": "",
        "paragraph_3_watch": "",
        "paragraph_4_buried": "",
        "ground_truth": "",
        "edition": "fact",
    }
    if "figures-differ" in labels:
        card["has_figure_conflict"] = True
    return card


def attach_story_cards(brief):
    for section in ("events", "single_outlet", "statements"):
        for event in brief.get(section) or []:
            event["story_card"] = event_to_story_card(event, section=section)
    brief["top_stories"] = [event["story_card"] for event in (brief.get("events") or [])]
    brief["story_cards"] = {
        "events": [event["story_card"] for event in (brief.get("events") or [])],
        "single_outlet": [event["story_card"] for event in (brief.get("single_outlet") or [])],
        "statements": [event["story_card"] for event in (brief.get("statements") or [])],
    }
    return brief


def assemble_brief(articles, now=None):
    now = now or utc_now()
    for article in articles:
        lat, lon = keep_coordinates(article.get("title"), article.get("lat"), article.get("lon"))
        article["lat"] = lat
        article["lon"] = lon
    clusters = cluster_articles(articles)
    events = []
    single = []
    statements = []
    for cluster in clusters:
        report_text = " ".join(article.get("title", "") + " " + article.get("summary", "") for article in cluster if article["standing"] != "record")
        records = [article for article in cluster if article["standing"] == "record"]
        confirmed = []
        nearby = []
        if report_text.strip():
            for record in records:
                if instrument_confirms(report_text, record):
                    confirmed.append(record)
                elif record.get("event_class") not in (None, "other") and event_class(report_text) not in (None, "other", record.get("event_class")):
                    report_point = None
                    places = specific_places(report_text)
                    if places:
                        report_point = GAZETTEER[max(places, key=len)]
                    if report_point and record.get("lat") is not None:
                        distance = haversine_km(report_point[0], report_point[1], float(record["lat"]), float(record["lon"]))
                        if distance <= 80:
                            nearby.append(record)
        else:
            confirmed = records
        conflicts = conflicting_figures([article for article in cluster if article["standing"] != "record"] or cluster)
        promoting = confirmed if report_text.strip() else records
        labels = _labels(cluster, promoting, conflicts)
        reports = unique_sources(cluster, "report")
        point = None
        for article in confirmed + records + cluster:
            if article.get("lat") is not None and article.get("lon") is not None:
                point = (float(article["lat"]), float(article["lon"]))
                break
        published_values = [article["published"] for article in cluster if article.get("published")]
        event = {
            "id": _event_id(cluster),
            "labels": labels,
            "headline": choose_headline(cluster),
            "paragraphs": _paragraphs(cluster, confirmed if report_text.strip() else records, nearby, conflicts),
            "published": max(published_values) if published_values else "",
            "independent_outlet_count": len(reports),
            "outlets": _outlets(cluster),
            "figures": conflicts,
            "lat": point[0] if point else None,
            "lon": point[1] if point else None,
            "instruments": [
                {
                    "source": article["source"],
                    "event_class": article.get("event_class"),
                    "observation": article.get("observation"),
                    "url": article.get("url") or "",
                    "lat": article.get("lat"),
                    "lon": article.get("lon"),
                    "confirms": article in confirmed,
                }
                for article in records
            ],
        }
        if "single-outlet" in labels and "sensor-confirmed" not in labels and "satellite-mapped" not in labels and "dataset-record" not in labels:
            event["topic"] = event_topic(event)
            single.append(event)
        elif labels == ["statement"]:
            event["topic"] = event_topic(event)
            statements.append(event)
        elif labels:
            event["topic"] = event_topic(event)
            events.append(event)
    events, truncated_environment = prioritize_events(events)
    single = prioritize_singles(single)
    statements.sort(key=lambda item: item.get("published") or "", reverse=True)
    trimmed = truncated_environment or len(events) >= MAX_EVENTS
    return {
        "edition": "fact",
        "rules_version": 2,
        "date": now.strftime("%A %d %B %Y"),
        "generated_at_iso": now.isoformat(),
        "generated_by": "Vantage fact brief",
        "headline_brief": "",
        "method": METHOD,
        "priority_topics": ["conflict-war", "persecution", "stability", "economics"],
        "events": events,
        "single_outlet": single,
        "statements": statements[:MAX_STATEMENTS],
        "truncated": trimmed,
        "imagery_note": IMAGERY_NOTE,
    }


def _fill_counts(brief, source_log):
    brief["headline_brief"] = (
        f"{len(brief['events'])} corroborated or recorded items, "
        f"{len(brief['single_outlet'])} single-outlet reports, "
        f"{len(brief['statements'])} statements"
    )
    topic_counts = {}
    for event in brief.get("events") or []:
        topic = event.get("topic") or event_topic(event)
        event["topic"] = topic
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
    brief["counts"] = {
        "events": len(brief["events"]),
        "single_outlet": len(brief["single_outlet"]),
        "statements": len(brief["statements"]),
        "sensor_confirmed": sum("sensor-confirmed" in event["labels"] for event in brief["events"]),
        "satellite_mapped": sum("satellite-mapped" in event["labels"] for event in brief["events"]),
        "figures_differ": sum("figures-differ" in event["labels"] for event in brief["events"]),
        "by_topic": topic_counts,
        "war": topic_counts.get("conflict-war", 0),
        "economy": topic_counts.get("economics", 0),
        "persecution": topic_counts.get("persecution", 0),
        "stability": topic_counts.get("stability", 0),
        "environment": topic_counts.get("environment", 0),
    }
    brief["sources"] = source_log
    if brief["truncated"]:
        brief["method"] += f" When more than {MAX_EVENTS} items qualify, the {MAX_EVENTS} with the most independent outlets are kept."


def attach_imagery(brief, lookup=None):
    lookup = lookup or lookup_sentinel
    checked = 0
    errors = []
    firms_state = "not_configured" if not os.environ.get("NASA_FIRMS_MAP_KEY") else "not_needed"
    for event in brief["events"]:
        if checked >= 6 or event.get("lat") is None:
            continue
        if not any(label in event["labels"] for label in ("sensor-confirmed", "satellite-mapped", "dataset-record")):
            continue
        scene, error = lookup(event["lat"], event["lon"])
        checked += 1
        if error:
            errors.append(error)
        if scene:
            event["imagery"] = scene
            event["paragraphs"].append(scene["note"])
        if re.search(r"\b(wildfire|bushfire|forest fire)\b", event.get("headline", ""), re.I) and os.environ.get("NASA_FIRMS_MAP_KEY"):
            count, firms_error = fetch_firms_count(event["lat"], event["lon"])
            firms_state = "queried"
            if firms_error:
                firms_state = firms_error
            elif count:
                event["paragraphs"].append(
                    f"NASA FIRMS listed {count} thermal detections within 0.4 degrees of this point over the last 2 days."
                )
                if "sensor-confirmed" not in event["labels"]:
                    event["labels"].append("sensor-confirmed")
    brief["checks"] = brief.get("checks") or {}
    brief["checks"]["sentinel2"] = "error" if errors and checked else ("queried" if checked else "not_run")
    if errors:
        brief["checks"]["sentinel2_error"] = errors[0]
    brief["checks"]["firms"] = firms_state
    return brief


def build_fact_brief(now=None):
    now = now or utc_now()
    articles = []
    source_log = []

    def _take(feed_name, standing, fetched):
        rows, error = fetched
        source_log.append({
            "name": feed_name,
            "standing": standing,
            "items": len(rows),
            "error": error,
        })
        articles.extend(rows)

    jobs = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        for feed in FACT_FEEDS:
            jobs.append((feed["source"], feed["standing"], pool.submit(fetch_feed, feed, now)))
        jobs.append(("USGS", "record", pool.submit(fetch_usgs, now)))
        jobs.append(("NASA EONET", "record", pool.submit(fetch_eonet, now)))
        jobs.append(("GDACS", "record", pool.submit(fetch_gdacs, now)))
        jobs.append(("Copernicus EMS", "record", pool.submit(fetch_copernicus, now)))
        jobs.append(("ACLED", "record", pool.submit(fetch_acled, now)))
        for name, standing, future in jobs:
            try:
                _take(name, standing, future.result())
            except Exception as exc:
                source_log.append({"name": name, "standing": standing, "items": 0, "error": str(exc.__class__.__name__)})
    brief = assemble_brief(articles, now=now)
    _fill_counts(brief, source_log)
    brief["checks"] = {
        "acled": "queried" if os.environ.get("ACLED_API_KEY") and os.environ.get("ACLED_EMAIL") else "not_configured",
        "firms": "not_configured" if not os.environ.get("NASA_FIRMS_MAP_KEY") else "available",
    }
    try:
        attach_imagery(brief)
    except Exception as exc:
        brief["checks"]["sentinel2"] = str(exc.__class__.__name__)
    attach_story_cards(brief)
    return brief
