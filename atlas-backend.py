# ── v114: Atlas Economic Intelligence Engine ──
# Append this entire block to the END of main.py
# DO NOT edit any existing code above

import json5

ATLAS_FILE = os.path.join(VOLUME_PATH, 'atlas.json') if 'VOLUME_PATH' in dir() else 'atlas.json'

@app.route('/atlas.json')
def serve_atlas():
    """Serve the atlas data file"""
    try:
        if os.path.exists(ATLAS_FILE):
            with open(ATLAS_FILE, 'r') as f:
                return f.read(), 200, {'Content-Type': 'application/json'}
        else:
            return jsonify({'error': 'Atlas not generated yet. Use /trigger-atlas to generate.', 'regions': []}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/trigger-atlas')
def trigger_atlas():
    """Generate atlas economic profiles for all regions. COSTS API MONEY."""
    try:
        atlas_data = generate_atlas()
        return jsonify({'status': 'ok', 'regions': len(atlas_data.get('regions', []))})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})

def generate_atlas():
    """Generate economic intelligence profiles for all regions and key countries."""
    regions = [
        {'name': 'Middle East', 'countries': ['Iran', 'Saudi Arabia', 'UAE', 'Iraq', 'Turkey', 'Israel', 'Qatar', 'Egypt']},
        {'name': 'Europe', 'countries': ['Germany', 'France', 'UK', 'Italy', 'Poland', 'Ukraine']},
        {'name': 'East Asia', 'countries': ['China', 'Japan', 'South Korea', 'Taiwan', 'North Korea']},
        {'name': 'South Asia', 'countries': ['India', 'Pakistan', 'Bangladesh', 'Sri Lanka']},
        {'name': 'Africa', 'countries': ['Nigeria', 'South Africa', 'Ethiopia', 'Kenya', 'Egypt', 'DRC']},
        {'name': 'Americas', 'countries': ['United States', 'Brazil', 'Mexico', 'Argentina', 'Canada', 'Venezuela']},
        {'name': 'Russia · Eurasia', 'countries': ['Russia', 'Kazakhstan', 'Uzbekistan', 'Georgia', 'Belarus']}
    ]

    atlas = {
        'generated_at': datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC'),
        'sources': 'IMF, World Bank, Trading Economics, OECD, National Statistics',
        'regions': []
    }

    for region_def in regions:
        print(f"[ATLAS] Generating region: {region_def['name']}")
        try:
            region_data = generate_atlas_region(region_def)
            atlas['regions'].append(region_data)
        except Exception as e:
            print(f"[ATLAS] Error generating {region_def['name']}: {e}")
            atlas['regions'].append({'name': region_def['name'], 'health_score': 50, 'summary': 'Generation failed', 'countries': [], 'metrics': [], 'cascading_effects': []})

    # Save to file
    with open(ATLAS_FILE, 'w') as f:
        json.dump(atlas, f, indent=2)
    print(f"[ATLAS] Saved atlas.json with {len(atlas['regions'])} regions")
    return atlas

def generate_atlas_region(region_def):
    """Generate a single region profile with countries."""
    region_name = region_def['name']
    countries_list = ', '.join(region_def['countries'])

    prompt = f"""You are an economic intelligence analyst. Generate a comprehensive economic profile for the {region_name} region and its key countries: {countries_list}.

Use your knowledge and any available current data. Today's date is {datetime.now(timezone.utc).strftime('%d %B %Y')}.

Respond ONLY with valid JSON. No markdown, no backticks, no explanation outside the JSON.

The JSON must have this EXACT structure (all values are strings or numbers, NO nested objects inside metrics):

{{
  "name": "{region_name}",
  "health_score": 55,
  "summary": "brief one-line summary",
  "assessment": "2-3 paragraph regional economic assessment with specific data points, connections between economies, and structural analysis",
  "meta": [
    {{"label": "Regional GDP", "value": "$X.XT combined"}},
    {{"label": "Dominant", "value": "Country ($XB)"}},
    {{"label": "Key Export", "value": "commodity (X%)"}},
    {{"label": "Integration", "value": "trade bloc name"}},
    {{"label": "Contagion Risk", "value": "X.X / 10"}}
  ],
  "health_factors": [
    {{"name": "GDP trajectory", "value": 45}},
    {{"name": "Trade flow", "value": 50}},
    {{"name": "Currency stability", "value": 55}},
    {{"name": "Fiscal position", "value": 40}},
    {{"name": "Energy resilience", "value": 35}},
    {{"name": "Structural stability", "value": 50}}
  ],
  "metrics": [
    {{
      "name": "Avg GDP Growth",
      "current": "-0.8%",
      "baseline": "+3.2%",
      "baseline_label": "Pre-crisis",
      "direction": "▼ CONTRACT",
      "direction_class": "db",
      "status": "critical",
      "category": "region",
      "why": "explanation of why this metric is at this level",
      "cascade": "if X happens then Y follows",
      "source": "IMF, World Bank"
    }}
  ],
  "cascading_effects": [
    "If X happens in country A, then Y follows in country B because Z connection exists"
  ],
  "countries": [
    {{
      "id": "country-name-slug",
      "name": "Country Name",
      "health_score": 45,
      "summary": "$XB GDP · brief status"
    }}
  ]
}}

REGIONAL METRICS must include ALL of these (11 total):
1. Avg GDP Growth - regional aggregate
2. Intra-Regional Trade Volume - trade between countries in region
3. Regional Integration Score - how coordinated is economic policy (0-10)
4. Key Export Revenue status - is main export flowing or disrupted
5. Commodity Price Exposure - how dependent on single commodity
6. Regional Contagion Risk - how likely one country's crisis spreads (0-10)
7. Migration Flows - net migration within/from region
8. Shared Infrastructure Vulnerability - chokepoints, pipelines, grids
9. Regional Currency Dynamics - pegs, devaluations, divergence
10. Cross-Border Conflict Economic Cost - if applicable
11. Regional Development Bank Activity - lending trends

For each metric include: name, current, baseline, baseline_label, direction, direction_class (ub/db/ug/dg/st/cr), status (critical/declining/caution/stable/improving), category, why, cascade (optional), source.

For cascading_effects: include 3-5 specific "If X then Y" chains showing how economies interconnect.

For countries: include each country with health_score (0-100) and a brief summary. Country details will be generated separately."""

    result = call_claude(prompt, max_tokens=6000)
    if not result:
        return {'name': region_name, 'health_score': 50, 'summary': 'No data', 'countries': [], 'metrics': [], 'cascading_effects': []}

    try:
        region_data = json.loads(result)
    except:
        try:
            region_data = json5.loads(result)
        except Exception as e:
            print(f"[ATLAS] JSON parse failed for {region_name}: {e}")
            return {'name': region_name, 'health_score': 50, 'summary': 'Parse error', 'countries': [], 'metrics': [], 'cascading_effects': []}

    # Now generate each country
    for i, country_stub in enumerate(region_data.get('countries', [])):
        country_name = country_stub.get('name', '')
        if not country_name:
            continue
        print(f"[ATLAS]   Generating country: {country_name}")
        try:
            country_data = generate_atlas_country(country_name, region_name)
            # Merge stub data with full country data
            country_data['id'] = country_stub.get('id', country_name.lower().replace(' ', '-'))
            country_data['summary'] = country_stub.get('summary', '')
            region_data['countries'][i] = country_data
        except Exception as e:
            print(f"[ATLAS]   Error generating {country_name}: {e}")

    return region_data

def generate_atlas_country(country_name, region_name):
    """Generate a full country economic profile with all metrics."""

    prompt = f"""You are an economic intelligence analyst. Generate a comprehensive economic profile for {country_name} in the {region_name} region.

Use your knowledge and current data. Today is {datetime.now(timezone.utc).strftime('%d %B %Y')}.

Respond ONLY with valid JSON. No markdown, no backticks.

{{
  "name": "{country_name}",
  "health_score": 45,
  "assessment": "2-3 paragraph country economic assessment with specific numbers, causal analysis, and outlook",
  "meta": [
    {{"label": "Population", "value": "XX.XM"}},
    {{"label": "GDP", "value": "$XXXB"}},
    {{"label": "Rating", "value": "AA/BBB/etc"}},
    {{"label": "Regime", "value": "type"}},
    {{"label": "Sanctions", "value": "status or None"}},
    {{"label": "Median Age", "value": "XX.X"}}
  ],
  "health_factors": [
    {{"name": "GDP growth", "value": 30}},
    {{"name": "Inflation", "value": 25}},
    {{"name": "Currency", "value": 40}},
    {{"name": "Employment", "value": 35}},
    {{"name": "Reserves", "value": 50}},
    {{"name": "Trade balance", "value": 30}},
    {{"name": "Food security", "value": 45}},
    {{"name": "Structural", "value": 40}}
  ],
  "sections": [
    {{
      "title": "Core Economic Indicators",
      "category": "core",
      "metrics": [
        {{
          "name": "GDP Growth",
          "current": "-X.X%",
          "baseline": "+X.X%",
          "baseline_label": "Pre-crisis",
          "direction": "▼ CONTRACT",
          "direction_class": "db",
          "status": "critical",
          "category": "core",
          "why": "specific explanation with data",
          "cascade": "if X then Y",
          "source": "IMF, national statistics"
        }}
      ]
    }}
  ],
  "cascading_effects": [
    "If X metric crosses Y threshold, then Z consequence follows because of W connection"
  ]
}}

SECTIONS must include exactly these 4 sections with ALL listed metrics:

SECTION 1 - "Core Economic Indicators" (category: "core") - 16 metrics:
GDP Growth, Inflation (Real), Unemployment, Currency vs USD, Foreign Reserves, Interest Rate, Debt-to-GDP, Trade Balance, Budget Deficit, Wage Growth (Real), Consumer Confidence, Manufacturing PMI, Services PMI, Household Debt, Income Inequality (Gini), Poverty Rate, Subsidy Spending, Shadow Economy, Capital Flight, Remittances

SECTION 2 - "Market Indicators" (category: "market") - 5 metrics:
Stock Market Index, Housing Market, Bond Yields, Credit Rating, FDI Inflows/Outflows

SECTION 3 - "Structural Indicators" (category: "structural") - 10 metrics:
Energy Export Dependence, Commodity Dependence, Demographics (show pop growth rate AND dependency ratio as visible numbers), Corruption Index, Ease of Business, Digital Economy, Central Bank Independence, Sovereign Wealth Fund, Social Spending Trajectory, Climate Vulnerability

SECTION 4 - "Vulnerability & Geopolitical" (category: "vulnerability") - 8 metrics:
Food Import Dependency, Water Stress, Energy Grid Vulnerability, Brain Drain, Military Spending pct GDP, Sanctions Exposure, Protest/Strike Frequency, Supply Chain Criticality, Belt and Road Debt, Aid Dependence, Diaspora Influence, Refugee Burden

For EVERY metric provide: name, current (specific number), baseline (comparison), baseline_label, direction (use symbols like ▲ ▼ ◆ →), direction_class (ub/db/ug/dg/st/cr), status (critical/declining/caution/stable/improving), category, why (2-3 sentences with specific data), cascade (1-2 sentences if X then Y), source.

Include 4-6 cascading_effects showing cross-metric and cross-country chains.

Be specific with numbers. Use real data. When uncertain, note estimates."""

    result = call_claude(prompt, max_tokens=6000)
    if not result:
        return {'name': country_name, 'health_score': 50, 'assessment': 'Generation failed', 'sections': [], 'cascading_effects': []}

    try:
        country_data = json.loads(result)
    except:
        try:
            country_data = json5.loads(result)
        except Exception as e:
            print(f"[ATLAS] JSON parse failed for {country_name}: {e}")
            return {'name': country_name, 'health_score': 50, 'assessment': 'Parse error', 'sections': [], 'cascading_effects': []}

    return country_data
