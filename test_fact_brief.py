import unittest

from fact_brief import (
    FACT_FEEDS,
    IMAGERY_NOTE,
    METHOD,
    assemble_brief,
    attach_story_cards,
    event_topic,
    include_nhc_title,
    instrument_confirms,
    parse_feed_items,
)


def article(title, source, org, standing="report", summary="", event_class="other", lat=None, lon=None, observation=None, published="2026-10-19T12:00:00+00:00"):
    return {
        "title": title,
        "summary": summary,
        "url": f"https://example.test/{org}/{title[:24].replace(' ', '-')}",
        "source": source,
        "org": org,
        "standing": standing,
        "published": published,
        "event_class": event_class,
        "lat": lat,
        "lon": lon,
        "observation": observation,
    }


class FactBriefTests(unittest.TestCase):
    def test_two_outlets_are_included_and_one_is_not(self):
        brief = assemble_brief([
            article("Ceasefire talks resume in Gaza", "BBC", "bbc"),
            article("Ceasefire talks resume in Gaza", "France 24", "france24"),
            article("Port workers strike in Marseille", "NHK", "nhk"),
        ])
        headlines = [event["headline"] for event in brief["events"]]
        self.assertIn("Ceasefire talks resume in Gaza", headlines)
        self.assertNotIn("Port workers strike in Marseille", headlines)
        single = brief["single_outlet"][0]
        self.assertEqual(single["headline"], "Port workers strike in Marseille")
        self.assertEqual(single["labels"], ["single-outlet"])
        event = next(item for item in brief["events"] if "Gaza" in item["headline"])
        self.assertEqual(event["independent_outlet_count"], 2)
        self.assertIn("multi-source", event["labels"])
        self.assertIn("Reported by 2 independent outlets: BBC, France 24.", event["paragraphs"])

    def test_state_outlet_does_not_corroborate(self):
        brief = assemble_brief([
            article("Talks on a grain corridor reopen", "BBC", "bbc"),
            article("Talks on a grain corridor reopen", "TASS", "tass", standing="statement"),
        ])
        self.assertEqual(brief["events"], [])
        self.assertEqual(brief["single_outlet"][0]["independent_outlet_count"], 1)
        self.assertIn("not counted as confirmation", " ".join(brief["single_outlet"][0]["paragraphs"]))

    def test_statement_alone_stays_a_statement(self):
        brief = assemble_brief([
            article("IAEA board opens its meeting", "IAEA", "iaea", standing="statement"),
        ])
        self.assertEqual(brief["events"], [])
        self.assertEqual(brief["statements"][0]["labels"], ["statement"])

    def test_earthquake_sensor_confirms_same_place_not_another_story(self):
        quake = article(
            "M 6.0 - 186 km NW of Port-Olry, Vanuatu",
            "USGS",
            "usgs",
            standing="record",
            event_class="earthquake",
            lat=-14.05,
            lon=165.68,
            observation="USGS recorded a magnitude 6.0 earthquake, 186 km NW of Port-Olry, Vanuatu, at 2026-10-19T07:49:00+00:00. Review status on the USGS record: reviewed.",
        )
        brief = assemble_brief([
            article("Magnitude 6.0 earthquake strikes Vanuatu", "BBC", "bbc", summary="A magnitude 6.0 earthquake struck near Vanuatu."),
            article("Parliament in Vanuatu opens a budget session", "France 24", "france24"),
            quake,
        ])
        quake_event = next(item for item in brief["events"] if "earthquake" in item["headline"].lower())
        self.assertIn("sensor-confirmed", quake_event["labels"])
        self.assertTrue(any(row["confirms"] for row in quake_event["instruments"]))
        budget = next(item for item in brief["single_outlet"] if "budget" in item["headline"])
        self.assertNotIn("sensor-confirmed", budget["labels"])
        self.assertFalse(instrument_confirms("Parliament in Vanuatu opens a budget session", quake))

    def test_distant_fire_in_a_large_country_is_not_confirmation(self):
        fire = article(
            "Wildfire in California",
            "NASA EONET",
            "eonet",
            standing="record",
            event_class="fire",
            lat=36.8,
            lon=-119.4,
            observation="NASA EONET lists a wildfire in California.",
        )
        self.assertTrue(instrument_confirms("Wildfire spreads in California", fire))
        self.assertFalse(instrument_confirms("Wildfire spreads in Florida", fire))

    def test_disagreeing_casualty_figures_are_both_kept(self):
        brief = assemble_brief([
            article("Blast hits a market in Khartoum", "BBC", "bbc", summary="Officials said 12 people were killed."),
            article("Blast hits a market in Khartoum", "Al Jazeera", "aljazeera", summary="Medics said 40 people were killed."),
        ])
        event = brief["events"][0]
        self.assertIn("figures-differ", event["labels"])
        text = " ".join(event["paragraphs"])
        self.assertIn("BBC published 12 killed", text)
        self.assertIn("Al Jazeera published 40 killed", text)
        self.assertNotIn("death toll is", text.lower())

    def test_templates_do_not_add_an_assessment(self):
        brief = assemble_brief([
            article("Ceasefire talks resume in Gaza", "BBC", "bbc"),
            article("Ceasefire talks resume in Gaza", "Reuters", "reuters"),
        ])
        wrappers = [p for p in brief["events"][0]["paragraphs"] if p != brief["events"][0]["headline"]]
        banned = ("should", "likely", "significant", "threat", "expect", "probably", "recommend", "we think", "urgent")
        for paragraph in wrappers:
            low = paragraph.lower()
            for word in banned:
                self.assertNotIn(word, low)
        self.assertNotIn("we think", METHOD.lower())
        self.assertIn("not interpreted", IMAGERY_NOTE)

    def test_commentary_feeds_are_not_sources(self):
        names = {feed["source"].lower() for feed in FACT_FEEDS}
        for excluded in ("seymour hersh", "isw", "war on the rocks", "caitlin johnstone", "substack"):
            self.assertNotIn(excluded, names)

    def test_priority_topics_outrank_environment_sensors(self):
        brief = assemble_brief([
            article("Ceasefire talks resume in Gaza", "BBC", "bbc"),
            article("Ceasefire talks resume in Gaza", "France 24", "france24"),
            article("Inflation cools in the euro area", "FT", "ft", summary="Consumer prices fell and markets rose."),
            article("Inflation cools in the euro area", "Bloomberg", "bloomberg", summary="Central bank data showed inflation easing."),
            article(
                "Crackdown detains hundreds of political prisoners",
                "HRW", "hrw", summary="A human rights crackdown and mass detention were reported.",
            ),
            article(
                "Crackdown detains hundreds of political prisoners",
                "Amnesty International", "amnesty", summary="Persecution and detention of opponents continued.",
            ),
            article(
                "M 6.0 - 186 km NW of Port-Olry, Vanuatu",
                "USGS", "usgs", standing="record", event_class="earthquake",
                lat=-14.05, lon=165.67,
                observation="USGS recorded a magnitude 6.0 earthquake near Vanuatu.",
            ),
            article(
                "Green flood alert in Spain",
                "GDACS", "gdacs", standing="record", event_class="flood",
                lat=41.4, lon=2.2,
                observation="GDACS published: Green flood alert in Spain.",
            ),
            article(
                "Tropical Storm Trudy Public Advisory Number 24",
                "NHC Pacific", "nhc", standing="record", event_class="storm",
                observation="NHC Pacific published: Tropical Storm Trudy Public Advisory Number 24.",
            ),
        ])
        topics = [event.get("topic") or event_topic(event) for event in brief["events"]]
        self.assertIn("conflict-war", topics)
        self.assertIn("economics", topics)
        self.assertIn("persecution", topics)
        self.assertLessEqual(topics.count("environment"), 5)
        # First items should be priority topics, not storms/quakes.
        top_topics = [event_topic(event) for event in brief["events"][:3]]
        self.assertTrue(all(topic != "environment" for topic in top_topics))
        self.assertIn("Priority topics are war, economy, persecution, and stability", METHOD)

    def test_story_cards_are_attached_without_analysis(self):
        brief = assemble_brief([
            article("Ceasefire talks resume in Gaza", "BBC", "bbc"),
            article("Ceasefire talks resume in Gaza", "France 24", "france24"),
            article(
                "M 6.0 - 186 km NW of Port-Olry, Vanuatu",
                "USGS", "usgs", standing="record", event_class="earthquake",
                lat=-14.05, lon=165.67,
                observation="USGS recorded a magnitude 6.0 earthquake near Vanuatu.",
            ),
        ])
        attach_story_cards(brief)
        self.assertEqual(len(brief["top_stories"]), 2)
        card = next(item for item in brief["top_stories"] if "Gaza" in item["headline"])
        self.assertEqual(card["confidence_badge"], "MULTI-SOURCE")
        self.assertEqual(card["sources"], ["BBC", "France 24"])
        self.assertEqual(card["who_benefits"], None)
        self.assertEqual(card["significance"], "")
        self.assertEqual(card["edition"], "fact")
        quake = next(item for item in brief["top_stories"] if "Vanuatu" in item["headline"])
        self.assertEqual(quake["confidence_badge"], "SENSOR RECORD")
        self.assertEqual(quake["category"], "environment")

    def test_routine_hurricane_outlook_is_excluded_and_products_collapse(self):
        self.assertFalse(include_nhc_title("There are no tropical cyclones at this time."))
        self.assertFalse(include_nhc_title("Tropical Storm Trudy Graphics"))
        self.assertFalse(include_nhc_title("Tropical Storm Trudy Forecast Discussion Number 24"))
        self.assertIn("magnitude 5.5", METHOD)
        self.assertIn("forest-fire notifications", METHOD)
        self.assertTrue(include_nhc_title("Tropical Storm Trudy Public Advisory Number 24"))
        brief = assemble_brief([
            article("Tropical Storm Trudy Public Advisory Number 24", "NHC Pacific", "nhc", standing="record", event_class="storm", observation="NHC Pacific published the public advisory for Tropical Storm Trudy."),
            article("Tropical Storm Trudy Graphics", "NHC Pacific", "nhc", standing="record", event_class="storm", observation="NHC Pacific published graphics for Tropical Storm Trudy."),
            article("Hurricane Trudy", "NASA EONET", "eonet", standing="record", event_class="storm", lat=-15.0, lon=-163.0, observation="NASA EONET lists Hurricane Trudy."),
        ])
        self.assertEqual(len(brief["events"]), 1)
        self.assertIn("Public Advisory", brief["events"][0]["headline"])
        self.assertIn("sensor-confirmed", brief["events"][0]["labels"])

    def test_rss1_items_parse(self):
        xml = b"""<?xml version="1.0"?>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
          <item>
            <title>Ceasefire talks resume</title>
            <link>https://example.test/a</link>
            <dc:date>2026-10-19T12:00:00Z</dc:date>
            <description>Talks resumed.</description>
          </item>
        </rdf:RDF>"""
        items = parse_feed_items(xml)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Ceasefire talks resume")
        self.assertEqual(items[0]["published_raw"], "2026-10-19T12:00:00Z")

    def test_magnitude_notation_and_bad_coordinates(self):
        brief = assemble_brief([
            article(
                "M 5.7 - 48 km WNW of Khuzdar, Pakistan",
                "USGS", "usgs", standing="record", event_class="earthquake",
                lat=28.02, lon=66.17,
                summary="USGS recorded a magnitude 5.7 earthquake in Pakistan.",
                observation="USGS recorded a magnitude 5.7 earthquake in Pakistan.",
            ),
            article(
                "Green earthquake (Magnitude 5.7M, Depth:10km) in Pakistan",
                "GDACS", "gdacs", standing="record", event_class="earthquake",
                lat=28.05, lon=66.2,
                summary="The earthquake had Magnitude 5.7M, Depth:10km.",
                observation="GDACS published: Green earthquake (Magnitude 5.7M, Depth:10km) in Pakistan.",
            ),
            article(
                "Green flood alert in Spain",
                "GDACS", "gdacs", standing="record", event_class="flood",
                lat=5.37, lon=100.46,
                observation="GDACS published: Green flood alert in Spain.",
            ),
        ])
        pakistan = next(event for event in brief["events"] if "Pakistan" in event["headline"])
        self.assertNotIn("figures-differ", pakistan["labels"])
        spain = next(event for event in brief["events"] if "Spain" in event["headline"])
        self.assertIsNone(spain["lat"])
        self.assertIsNone(spain["lon"])
        split = assemble_brief([
            article("Green flood alert in Spain", "GDACS", "gdacs", standing="record", event_class="flood", lat=41.4, lon=2.2, observation="GDACS published: Green flood alert in Spain."),
            article("Green flood alert in Malaysia", "GDACS", "gdacs", standing="record", event_class="flood", lat=5.4, lon=100.4, observation="GDACS published: Green flood alert in Malaysia."),
        ])
        self.assertEqual(len(split["events"]), 2)

    def test_distant_instrument_records_stay_separate(self):
        brief = assemble_brief([
            article(
                "M 6.0 - 186 km NW of Port-Olry, Vanuatu",
                "USGS", "usgs", standing="record", event_class="earthquake",
                lat=-14.05, lon=165.67,
                summary="USGS recorded a magnitude 6.0 earthquake, 186 km NW of Port-Olry, Vanuatu.",
                observation="USGS recorded a magnitude 6.0 earthquake, 186 km NW of Port-Olry, Vanuatu.",
            ),
            article(
                "M 5.7 - 48 km WNW of Khuzdar, Pakistan",
                "USGS", "usgs", standing="record", event_class="earthquake",
                lat=28.02, lon=66.17,
                summary="USGS recorded a magnitude 5.7 earthquake, 48 km WNW of Khuzdar, Pakistan.",
                observation="USGS recorded a magnitude 5.7 earthquake, 48 km WNW of Khuzdar, Pakistan.",
            ),
            article(
                "Green earthquake (Magnitude 5.7M, Depth:10km) in Pakistan",
                "GDACS", "gdacs", standing="record", event_class="earthquake",
                lat=28.05, lon=66.2,
                observation="GDACS published: Green earthquake (Magnitude 5.7M, Depth:10km) in Pakistan.",
            ),
        ])
        headlines = [event["headline"] for event in brief["events"]]
        self.assertTrue(any("Vanuatu" in headline for headline in headlines))
        self.assertTrue(any("Pakistan" in headline for headline in headlines))
        pakistan = next(event for event in brief["events"] if "Pakistan" in event["headline"])
        sources = {row["source"] for row in pakistan["instruments"]}
        self.assertEqual(sources, {"USGS", "GDACS"})
        self.assertEqual(len(brief["events"]), 2)

    def test_satellite_map_does_not_confirm_a_different_event_type(self):
        mapping = article(
            "Flood in Sudan",
            "Copernicus EMS",
            "copernicus-ems",
            standing="record",
            event_class="flood",
            lat=15.5,
            lon=32.5,
            observation="Copernicus Emergency Management Service activation EMSR100 lists 4 published map products.",
        )
        self.assertFalse(instrument_confirms("Cabinet meets in Khartoum", mapping))
        brief = assemble_brief([mapping])
        self.assertIn("satellite-mapped", brief["events"][0]["labels"])
        self.assertNotIn("sensor-confirmed", brief["events"][0]["labels"])


if __name__ == "__main__":
    unittest.main()
