#!/usr/bin/env python3
"""
Brittany VFR METAR/TAF Fetcher

Fetches METAR/TAF from aviation.meteo.fr (authenticated) for all Brittany airports,
ranks them by VFR conditions (best to worst), and displays in a table.

Requirements:
- Python 3.8+
- requests library (pip install requests)
- OurAirports CSV for airport list

Usage:
    python METAR.py


    What the script does:
    Downloads/loads the airports database (cached as airports.csv)
    Filters for 21 Brittany airports
    Logs into aviation.meteo.fr
    Fetches METAR/TAF data
    Displays ranked table by VFR conditions
    Prompts you to enter ICAO codes for detailed weather descriptions
    Type an ICAO (like LFRN or LFRB) and press Enter to see details
    Press Enter without typing to exit


Credentials can be provided via:
- Environment variables: METEO_USER and METEO_PASS
- Interactive prompt (secure, hidden input)
"""
import os
import sys
import csv
import re
import getpass
import hashlib
from typing import Optional
from dataclasses import dataclass

try:
    import requests
except ImportError:
    print("Error: requests library not found. Install with: pip install requests")
    sys.exit(1)


# OurAirports CSV URL
OURAIRPORTS_URL = "https://ourairports.com/data/airports.csv"
AIRPORTS_CACHE = "airports.csv"

# Brittany departments (for filtering French airports in the region)
BRITTANY_DEPTS = {'22', '29', '35', '56'}  # Côtes-d'Armor, Finistère, Ille-et-Vilaine, Morbihan

# aviation.meteo.fr endpoints
METEO_FR_BASE = "https://aviation.meteo.fr"
LOGIN_URL = f"{METEO_FR_BASE}/ajax/login_valid.php"
REPORT_URL = f"{METEO_FR_BASE}/dossier_personnalise_show_html.php"


@dataclass
class Airport:
    icao: str
    name: str
    lat: float
    lon: float
    region: str


@dataclass
class Weather:
    icao: str
    metar_raw: Optional[str]
    taf_raw: Optional[str]
    visibility_sm: Optional[float]
    ceiling_ft: Optional[int]
    flight_category: Optional[str]
    vfr_score: int  # Higher = better VFR (5=CAVOK, 4=VFR, 3=MVFR, 2=IFR, 1=LIFR, 0=No data)


def download_airports_csv(cache_path: str = AIRPORTS_CACHE) -> str:
    """Download OurAirports CSV if not cached."""
    if os.path.exists(cache_path):
        return cache_path
    print(f"Downloading airports database to {cache_path}...")
    resp = requests.get(OURAIRPORTS_URL, timeout=30)
    resp.raise_for_status()
    with open(cache_path, 'wb') as f:
        f.write(resp.content)
    print(f"Downloaded {len(resp.content)} bytes")
    return cache_path


def load_brittany_airports() -> list[Airport]:
    """Load ICAO airports in Brittany region from OurAirports CSV."""
    csv_path = download_airports_csv()
    airports = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ident = (row.get('ident') or '').strip().upper()
            
            # Filter: must be 4-letter ICAO starting with LF (France)
            if not (len(ident) == 4 and ident.startswith('LF')):
                continue
            
            # Filter by region: Brittany encompasses multiple approaches
            region = (row.get('iso_region') or '').strip()
            municipality = (row.get('municipality') or '').strip().lower()
            keywords = (row.get('keywords') or '').lower()
            
            # iso_region format: 'FR-BRE' for Bretagne or 'FR-22', 'FR-29', 'FR-35', 'FR-56'
            dept = region.split('-')[-1] if '-' in region else ''
            
            # Accept if:
            # 1. Region code is FR-BRE (Bretagne)
            # 2. Department is 22, 29, 35, or 56
            # 3. Municipality or keywords contain bretagne/brittany
            # 4. Specific major Brittany airports (whitelist)
            is_brittany = (
                region == 'FR-BRE' or
                dept in BRITTANY_DEPTS or
                'bretagne' in municipality or
                'brittany' in municipality or
                'bretagne' in keywords or
                'brittany' in keywords or
                ident in {'LFRN', 'LFRB', 'LFRT', 'LFRH', 'LFRV', 'LFES', 
                          'LFED', 'LFEQ', 'LFEB', 'LFRO', 'LFRP', 'LFRL', 
                          'LFRU', 'LFRQ', 'LFXQ', 'LFRZ'}  # Known Brittany ICAOs
            )
            
            if not is_brittany:
                continue
            
            try:
                lat = float(row.get('latitude_deg') or 0)
                lon = float(row.get('longitude_deg') or 0)
            except (ValueError, TypeError):
                continue
            
            airports.append(Airport(
                icao=ident,
                name=row.get('name', '').strip(),
                lat=lat,
                lon=lon,
                region=region
            ))
    
    print(f"Found {len(airports)} ICAO airports in Brittany")
    return airports


def get_credentials() -> tuple[str, str]:
    """Get aviation.meteo.fr credentials from env vars, credentials file, or interactive prompt."""
    user = os.environ.get('METEO_USER')
    password = os.environ.get('METEO_PASS')
    
    # If env vars not set, check for credentials.txt file
    if not user or not password:
        creds_file = os.path.join(os.path.dirname(__file__), 'credentials.txt')
        if os.path.exists(creds_file):
            try:
                with open(creds_file, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                    if len(lines) >= 2:
                        user = lines[0]
                        password = lines[1]
                        print(f"Loaded credentials from {creds_file}")
            except Exception as e:
                print(f"Warning: Could not read credentials file: {e}")
        else:
            # Create template file
            template = """# aviation.meteo.fr credentials
# Line 1: username
# Line 2: password
# IMPORTANT: Keep this file secure! Add to .gitignore if using version control.

your_username_here
your_password_here
"""
            try:
                with open(creds_file, 'w', encoding='utf-8') as f:
                    f.write(template)
                print(f"\n⚠️  Created template credentials file: {creds_file}")
                print("   Please edit it with your aviation.meteo.fr username and password.")
                print("   Then run this script again.\n")
            except Exception as e:
                print(f"Could not create credentials template: {e}")
    
    # Fall back to interactive prompt
    if not user:
        user = input("aviation.meteo.fr username: ").strip()
    if not password:
        password = getpass.getpass("aviation.meteo.fr password: ")
    
    return user, password


def login_meteo_fr(session: requests.Session, username: str, password: str) -> bool:
    """
    Authenticate with aviation.meteo.fr via AJAX login endpoint.
    The login returns a simple response (typically "OK" or error message).
    """
    print("Logging in to aviation.meteo.fr...")
    
    try:
        # First, visit the main page to get session cookies
        session.get(METEO_FR_BASE, timeout=10)
        
        # POST credentials to AJAX login endpoint
        # Based on inspection: login and pass are the form field names
        # IMPORTANT: Password must be MD5 hashed (JavaScript does this client-side)
        password_md5 = hashlib.md5(password.encode()).hexdigest()
        
        login_data = {
            'login': username,
            'password': password_md5,  # Note: form field is 'password', not 'pass'
        }
        
        headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': f'{METEO_FR_BASE}/login.php',
        }
        
        resp = session.post(LOGIN_URL, data=login_data, headers=headers, timeout=10)
        resp.raise_for_status()
        
        # Check response - typically returns "OK" on success or error message
        response_text = resp.text.strip()
        
        # Debug: check cookies
        print(f"  Cookies after login: {len(session.cookies)} cookies")
        for cookie in session.cookies:
            val = str(cookie.value) if cookie.value else ""
            print(f"    {cookie.name}: {val[:20]}...")
        
        if response_text == "OK" or resp.status_code == 200 and len(response_text) <= 3:
            print("Login successful")
            return True
        else:
            print(f"Login failed. Response: {response_text}")
            return False
    
    except requests.RequestException as e:
        print(f"Login error: {e}")
        return False


def fetch_all_metar_taf_from_report(session: requests.Session, icao_list: list[str], report_id: Optional[str] = None) -> dict[str, tuple[Optional[str], Optional[str]]]:
    """
    Fetch METAR/TAF for all airports by using a saved report.
    Returns dict: {ICAO: (metar_raw, taf_raw)}
    
    If report_id is provided, fetch that specific saved report.
    Otherwise, try to create a dynamic report.
    """
    results: dict[str, tuple[Optional[str], Optional[str]]] = {icao: (None, None) for icao in icao_list}
    
    try:
        if report_id:
            # Use saved report
            import time
            timestamp = str(int(time.time() * 1000))
            params = {
                'id': report_id,
                'origine': 'recents',
                'time': timestamp
            }
            resp = session.get(REPORT_URL, params=params, timeout=30)
        else:
            # Use the affichemessages.php endpoint which displays METAR/TAF
            # This is what the form on accueil.php uses (aero3 input field)
            stations_param = ' '.join(icao_list)
            
            params = {
                'mode': 'html',
                'codes': stations_param
            }
            
            resp = session.get(f"{METEO_FR_BASE}/affichemessages.php", params=params, timeout=30)
        
        if resp.status_code != 200:
            print(f"  Report fetch failed with status {resp.status_code}")
            # Save response for debugging
            with open('debug_response.html', 'w', encoding='utf-8') as f:
                f.write(f"Status: {resp.status_code}\n")
                f.write(f"URL: {resp.url}\n")
                f.write(f"Headers: {resp.headers}\n\n")
                f.write(resp.text)
            print(f"  Debug response saved to debug_response.html")
            return results
        
        html_text = resp.text
        
        # Save successful response for debugging
        with open('debug_response_success.html', 'w', encoding='utf-8') as f:
            f.write(html_text)
        print(f"  Response saved to debug_response_success.html ({len(html_text)} chars)")
        
        # Parse the HTML to extract METAR/TAF for each airport
        # HTML format from aviation.meteo.fr affichemessages.php:
        # <span class="texte3">ICAO</span> <span class="texte3">NAME</span><br>
        # <span class="texte2">METAR: </span><span class="texte1" style="">METAR text...<br>more lines...</span>
        # <span class="texte2">TAF LONG: </span><span class="texte1" style="">TAF text...</span>
        
        for icao in icao_list:
            metar_raw = None
            taf_raw = None
            
            # Find METAR for this ICAO
            # Pattern: <span class="texte2">METAR: </span><span class="texte1" style="">ICAO date ...<br>...</span>
            # The METAR starts with the ICAO code inside the texte1 span
            metar_pattern = rf'<span class="texte2">METAR:\s*</span><span class="texte1"[^>]*>({icao}\s+\d{{6}}Z[^<]*(?:<br[^>]*>[^<]*)*?)</span>'
            metar_match = re.search(metar_pattern, html_text, re.DOTALL | re.IGNORECASE)
            if metar_match:
                metar_raw = metar_match.group(1)
                # Clean up HTML tags and normalize whitespace
                metar_raw = re.sub(r'<br[^>]*>', ' ', metar_raw)
                metar_raw = re.sub(r'\s+', ' ', metar_raw)
                metar_raw = metar_raw.replace('&nbsp;', ' ').strip()
            
            # Find TAF for this ICAO (can be TAF LONG or TAF COURT)
            taf_pattern = rf'<span class="texte2">TAF\s+(?:LONG|COURT):\s*</span><span class="texte1"[^>]*>({icao}\s+\d{{6}}Z[^<]*(?:<br[^>]*>[^<]*)*?)</span>'
            taf_match = re.search(taf_pattern, html_text, re.DOTALL | re.IGNORECASE)
            if taf_match:
                taf_raw = taf_match.group(1)
                taf_raw = re.sub(r'<br[^>]*>', ' ', taf_raw)
                taf_raw = re.sub(r'\s+', ' ', taf_raw)
                taf_raw = taf_raw.replace('&nbsp;', ' ').strip()
            
            results[icao] = (metar_raw, taf_raw)
    
    except requests.RequestException as e:
        print(f"  Error fetching bulk report: {e}")
    
    return results


def fetch_metar_taf(session: requests.Session, icao: str) -> tuple[Optional[str], Optional[str]]:
    """
    Fetch METAR and TAF for a single ICAO code.
    This is a fallback for individual queries.
    """
    result = fetch_all_metar_taf_from_report(session, [icao])
    return result.get(icao, (None, None))


def parse_metar_vfr(metar_raw: Optional[str]) -> tuple[Optional[float], Optional[int], Optional[str]]:
    """
    Parse METAR for visibility (SM), ceiling (ft), and flight category.
    Returns: (visibility_sm, ceiling_ft, flight_category)
    """
    if not metar_raw:
        return None, None, None
    
    metar = metar_raw.upper()
    
    # Check CAVOK
    if 'CAVOK' in metar:
        return 10.0, None, 'CAVOK'
    
    # Parse visibility
    visibility_sm = None
    # Look for statute miles (e.g., 10SM)
    vis_match = re.search(r'\b(\d+(?:/\d+)?)SM\b', metar)
    if vis_match:
        vis_str = vis_match.group(1)
        if '/' in vis_str:
            num, denom = vis_str.split('/')
            visibility_sm = float(num) / float(denom)
        else:
            visibility_sm = float(vis_str)
    else:
        # Look for meters (e.g., 9999)
        vis_match = re.search(r'\b(\d{4})\b', metar)
        if vis_match:
            meters = int(vis_match.group(1))
            visibility_sm = meters * 0.000621371
    
    # Parse ceiling (lowest BKN or OVC layer)
    ceiling_ft = None
    cloud_pattern = re.compile(r'\b(BKN|OVC)(\d{3})\b')
    for match in cloud_pattern.finditer(metar):
        height = int(match.group(2)) * 100
        if ceiling_ft is None or height < ceiling_ft:
            ceiling_ft = height
    
    # Determine flight category
    flight_category = None
    if visibility_sm is not None or ceiling_ft is not None:
        vis = visibility_sm if visibility_sm is not None else 10.0
        ceil = ceiling_ft if ceiling_ft is not None else 10000
        
        if vis >= 5.0 and ceil >= 3000:
            flight_category = 'VFR'
        elif vis >= 3.0 and ceil >= 1000:
            flight_category = 'MVFR'
        elif vis >= 1.0 and ceil >= 500:
            flight_category = 'IFR'
        else:
            flight_category = 'LIFR'
    
    return visibility_sm, ceiling_ft, flight_category


def calculate_vfr_score(flight_category: Optional[str], metar_raw: Optional[str]) -> int:
    """Assign VFR score: higher = better conditions."""
    if not metar_raw:
        return 0  # No data
    if flight_category == 'CAVOK':
        return 5
    elif flight_category == 'VFR':
        return 4
    elif flight_category == 'MVFR':
        return 3
    elif flight_category == 'IFR':
        return 2
    elif flight_category == 'LIFR':
        return 1
    else:
        return 0


def fetch_all_weather(session: requests.Session, airports: list[Airport], report_id: Optional[str] = None) -> list[Weather]:
    """Fetch METAR/TAF for all airports and parse VFR conditions."""
    weather_data = []
    
    print(f"\nFetching METAR/TAF for {len(airports)} airports...")
    
    # Extract ICAO list
    icao_list = [airport.icao for airport in airports]
    
    # Fetch all in one bulk request
    if report_id:
        print(f"  Using saved report ID: {report_id}")
    else:
        print("  Attempting dynamic report fetch...")
    
    all_data = fetch_all_metar_taf_from_report(session, icao_list, report_id)
    
    # Build airport lookup
    airport_map = {a.icao: a for a in airports}
    
    # Process each airport
    for i, icao in enumerate(icao_list, 1):
        airport = airport_map[icao]
        metar_raw, taf_raw = all_data.get(icao, (None, None))
        
        visibility_sm, ceiling_ft, flight_category = parse_metar_vfr(metar_raw)
        vfr_score = calculate_vfr_score(flight_category, metar_raw)
        
        status = flight_category or ('No data' if not metar_raw else 'Unknown')
        print(f"  [{i}/{len(icao_list)}] {icao} - {airport.name[:30]:30} -> {status}")
        
        weather_data.append(Weather(
            icao=icao,
            metar_raw=metar_raw,
            taf_raw=taf_raw,
            visibility_sm=visibility_sm,
            ceiling_ft=ceiling_ft,
            flight_category=flight_category,
            vfr_score=vfr_score
        ))
    
    return weather_data


def display_ranked_table(weather_data: list[Weather], airports: list[Airport]):
    """Display ranked table of airports by VFR conditions."""
    # Sort by VFR score descending (best first)
    sorted_weather = sorted(weather_data, key=lambda w: w.vfr_score, reverse=True)
    
    # Build airport lookup
    airport_map = {a.icao: a for a in airports}
    
    print("\n" + "="*100)
    print("BRITTANY AIRPORTS RANKED BY VFR CONDITIONS (Best to Worst)")
    print("="*100)
    print(f"{'Rank':<6} {'ICAO':<6} {'Name':<30} {'Category':<8} {'Vis(SM)':<9} {'Ceil(ft)':<10} {'METAR':<30}")
    print("-"*100)
    
    for rank, weather in enumerate(sorted_weather, 1):
        airport = airport_map.get(weather.icao)
        name = airport.name[:28] if airport else weather.icao
        
        vis_str = f"{weather.visibility_sm:.1f}" if weather.visibility_sm else "-"
        ceil_str = str(weather.ceiling_ft) if weather.ceiling_ft else "-"
        metar_snippet = (weather.metar_raw[:28] + "..") if weather.metar_raw and len(weather.metar_raw) > 30 else (weather.metar_raw or "No data")
        
        print(f"{rank:<6} {weather.icao:<6} {name:<30} {weather.flight_category or 'N/A':<8} {vis_str:<9} {ceil_str:<10} {metar_snippet:<30}")
    
    print("="*100)
    print(f"\nLegend: CAVOK=Ceiling And Visibility OK, VFR=Visual Flight Rules, MVFR=Marginal VFR, IFR=Instrument Flight Rules, LIFR=Low IFR")
    print()


def describe_conditions(metar: str, category: Optional[str], visibility_sm: Optional[float], ceiling_ft: Optional[int]) -> None:
    """Décrit les conditions METAR en français avec explication détaillée de chaque terme."""
    metar_upper = metar.upper()
    
    # Catégorie générale
    if category == 'CAVOK':
        print("EXCELLENTES CONDITIONS VFR - Plafond et Visibilité OK")
        print("   Météo parfaite pour le vol à vue.")
    elif category == 'VFR':
        print("BONNES CONDITIONS VFR - Vol à Vue")
        print("   Bonnes conditions pour le vol à vue.")
    elif category == 'MVFR':
        print("CONDITIONS VFR MARGINALES")
        print("   Conditions limites pour le VFR. Prudence recommandée.")
    elif category == 'IFR':
        print("CONDITIONS IFR - Vol aux Instruments Requis")
        print("   Visibilité ou plafond trop bas pour le VFR.")
    elif category == 'LIFR':
        print("CONDITIONS IFR BASSES - Très mauvaise visibilité/plafond")
        print("   Restrictions sévères. Réservé aux pilotes IFR expérimentés.")
    
    print()
    
    # Visibilité
    if visibility_sm:
        # Note: 9999m dans le METAR = visibilité ≥10 km
        km = visibility_sm * 1.60934
        if km >= 9.9:  # Correspond à ~9999m
            print(f"VISIBILITE : 10+ km (superieure a 10 kilometres)")
            print("   Excellente visibilite.")
        else:
            print(f"VISIBILITE : {visibility_sm:.1f} miles terrestres ({km:.1f} km)")
            if visibility_sm >= 10:
                print("   Excellente visibilite.")
            elif visibility_sm >= 5:
                print("   Bonne visibilite pour le VFR.")
            elif visibility_sm >= 3:
                print("   Visibilite reduite. Surveillez les conditions.")
            else:
                print("   Mauvaise visibilite. Le vol VFR peut etre restreint.")
    
    # Plafond
    if ceiling_ft:
        print(f"PLAFOND : {ceiling_ft:,} pieds ({int(ceiling_ft * 0.3048)} mètres)")
        if ceiling_ft >= 5000:
            print("   Nuages hauts, excellent pour voler.")
        elif ceiling_ft >= 3000:
            print("   Bonne hauteur de plafond pour le VFR.")
        elif ceiling_ft >= 1000:
            print("   Plafond bas. Peut limiter les opérations VFR.")
        else:
            print("   Plafond très bas. Approches aux instruments peut-être nécessaires.")
    elif 'CAVOK' in metar_upper or 'SKC' in metar_upper or 'CLR' in metar_upper:
        print("PLAFOND : Ciel dégagé ou pas de nuages significatifs")
    
    # Vent (analyse détaillée)
    wind_match = re.search(r'\b(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT\b', metar_upper)
    wind_var_match = re.search(r'\b(\d{3})V(\d{3})\b', metar_upper)
    
    if wind_match:
        direction = wind_match.group(1)
        speed = int(wind_match.group(2))
        gust = int(wind_match.group(3)) if wind_match.group(3) else None
        
        print("VENT :")
        if direction == "VRB":
            print(f"   Direction : VRB (Variable) - le vent change constamment de direction")
        else:
            dir_name = get_wind_direction_name(direction)
            print(f"   Direction : {direction}° (depuis le {dir_name})")
        
        print(f"   Vitesse : {speed} KT (nœuds) = {int(speed * 1.852)} km/h")
        
        if gust:
            print(f"   Rafales : G{gust}KT = jusqu'à {gust} nœuds ({int(gust * 1.852)} km/h)")
            if gust > 25:
                print("   ATTENTION : Fortes rafales ! Prudence au décollage/atterrissage.")
            elif gust > 15:
                print("   Rafales modérées. Turbulence probable.")
        
        if wind_var_match:
            var_from = wind_var_match.group(1)
            var_to = wind_var_match.group(2)
            print(f"   Variation : {var_from}V{var_to} - vent variable entre {var_from}° et {var_to}°")
        
        # Composante de vent traversier (estimation générale)
        if speed > 20:
            print("   Vent fort - peut affecter les avions légers et les manœuvres.")
        elif speed > 10:
            print("   Vent modéré - normal pour les opérations.")
        elif speed < 3:
            print("   Vent calme ou très faible.")
        
        print()
    
    # Visibilité (analyse détaillée)
    vis_match = re.search(r'\b(\d{4})\b', metar_upper)
    if vis_match and 'CAVOK' not in metar_upper:
        vis_meters = vis_match.group(1)
        vis_m = int(vis_meters)
        print("VISIBILITE :")
        print(f"   Code : {vis_meters} (mètres)")
        
        if vis_m == 9999:
            print(f"   Signification : 10+ km (10 kilomètres ou plus - excellente)")
        else:
            vis_km = vis_m / 1000
            print(f"   Signification : {vis_m} mètres = {vis_km:.1f} km")
            if vis_m >= 5000:
                print("   Très bonne visibilité pour le VFR.")
            elif vis_m >= 3000:
                print("   Visibilité acceptable pour le VFR.")
            elif vis_m >= 1500:
                print("   Visibilité réduite - Vol VFR marginal.")
            else:
                print("   Mauvaise visibilité - Conditions IFR probables.")
        print()
    elif 'CAVOK' in metar_upper:
        print("VISIBILITE : CAVOK")
        print("   Signification : Ceiling And Visibility OK")
        print("   - Visibilité >= 10 km")
        print("   - Pas de nuages en-dessous de 5000 ft")
        print("   - Pas de CB (Cumulonimbus)")
        print("   - Pas de phénomènes météo significatifs")
        print()
    
    # Phénomènes météorologiques présents (analyse détaillée)
    weather_phenomena = []
    
    # Intensité
    intensity_map = {'+': 'Fort', '-': 'Faible', '': 'Modéré'}
    
    # Descripteurs
    descriptor_map = {
        'MI': 'Mince/Shallow',
        'PR': 'Partiel',
        'BC': 'Bancs',
        'DR': 'Chasse basse',
        'BL': 'Chasse haute',
        'SH': 'Averses',
        'TS': 'Orage',
        'FZ': 'Se congelant'
    }
    
    # Précipitations
    precip_map = {
        'DZ': 'Bruine',
        'RA': 'Pluie',
        'SN': 'Neige',
        'SG': 'Grains de neige',
        'IC': 'Cristaux de glace',
        'PL': 'Granules de glace',
        'GR': 'Grêle',
        'GS': 'Petite grêle/Neige roulée',
        'UP': 'Précipitation inconnue'
    }
    
    # Obscurcissement
    obscuration_map = {
        'BR': 'Brume',
        'FG': 'Brouillard',
        'FU': 'Fumée',
        'VA': 'Cendres volcaniques',
        'DU': 'Poussière répandue',
        'SA': 'Sable',
        'HZ': 'Brume sèche'
    }
    
    # Autres phénomènes
    other_map = {
        'PO': 'Tourbillons de poussière/sable',
        'SQ': 'Grains',
        'FC': 'Tornade/Trombe',
        'SS': 'Tempête de sable',
        'DS': 'Tempête de poussière'
    }
    
    # Recherche des phénomènes météo
    wx_pattern = r'\b([-+]?)(?:(MI|PR|BC|DR|BL|SH|TS|FZ))?(DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PO|SQ|FC|SS|DS)\b'
    wx_matches = re.finditer(wx_pattern, metar_upper)
    
    for match in wx_matches:
        intensity = match.group(1) or ''
        descriptor = match.group(2) or ''
        phenomenon = match.group(3)
        
        full_code = intensity + descriptor + phenomenon
        
        # Construction de la description
        desc_parts = []
        
        if intensity:
            desc_parts.append(intensity_map.get(intensity, ''))
        
        if descriptor:
            desc_parts.append(descriptor_map.get(descriptor, descriptor))
        
        # Phénomène principal
        main_desc = precip_map.get(phenomenon) or obscuration_map.get(phenomenon) or other_map.get(phenomenon) or phenomenon
        desc_parts.append(main_desc)
        
        weather_phenomena.append({
            'code': full_code,
            'description': ' '.join(desc_parts)
        })
    
    if weather_phenomena:
        print("PHENOMENES METEOROLOGIQUES :")
        for wx in weather_phenomena:
            print(f"   {wx['code']} : {wx['description']}")
            
            # Avertissements spécifiques
            if 'TS' in wx['code']:
                print("      ATTENTION : Orages - Activité électrique, turbulence sévère, cisaillement de vent")
            if 'FZ' in wx['code']:
                print("      ATTENTION : Conditions givrantes - Risque de givrage")
            if '+RA' in wx['code'] or '+SN' in wx['code']:
                print("      ATTENTION : Précipitations fortes - Visibilité fortement réduite")
            if 'FG' in wx['code']:
                print("      ATTENTION : Brouillard - Visibilité < 1000m")
        print()
    
    # Nuages (analyse détaillée de chaque couche)
    cloud_pattern = re.compile(r'\b(FEW|SCT|BKN|OVC|VV)(\d{3})(CB|TCU)?\b')
    cloud_matches = list(cloud_pattern.finditer(metar_upper))
    
    if cloud_matches:
        print("NUAGES :")
        
        coverage_map = {
            'FEW': 'FEW (Quelques nuages, 1-2 octas)',
            'SCT': 'SCT (Épars/Scattered, 3-4 octas)',
            'BKN': 'BKN (Fragmenté/Broken, 5-7 octas)',
            'OVC': 'OVC (Couvert/Overcast, 8 octas)',
            'VV': 'VV (Ciel invisible/Vertical Visibility)'
        }
        
        type_map = {
            'CB': 'CB (Cumulonimbus - nuages d\'orage)',
            'TCU': 'TCU (Towering Cumulus - cumulus bourgeonnant)'
        }
        
        for i, match in enumerate(cloud_matches, 1):
            coverage = match.group(1)
            height_code = match.group(2)
            cloud_type = match.group(3) or ''
            
            height_ft = int(height_code) * 100
            height_m = int(height_ft * 0.3048)
            
            print(f"   Couche {i} : {coverage}{height_code}{cloud_type}")
            print(f"      Couverture : {coverage_map.get(coverage, coverage)}")
            print(f"      Altitude : {height_ft} ft ({height_m} m) au-dessus du sol")
            
            if cloud_type:
                print(f"      Type : {type_map.get(cloud_type, cloud_type)}")
                if cloud_type == 'CB':
                    print("         ATTENTION : Cumulonimbus présents !")
                    print("         - Orages possibles")
                    print("         - Turbulence sévère")
                    print("         - Givrage possible")
                    print("         - Grêle possible")
                    print("         - Éviter absolument ces nuages")
                elif cloud_type == 'TCU':
                    print("         ATTENTION : Cumulus développés - turbulence probable")
            
            # Commentaire sur la hauteur
            if height_ft < 1000:
                print("         Nuages très bas - Peut limiter sérieusement le VFR")
            elif height_ft < 3000:
                print("         Nuages bas - Attention pour le VFR")
            elif height_ft >= 5000:
                print("         Nuages hauts - Bonne marge pour le VFR")
        
        print()
    elif 'CAVOK' not in metar_upper:
        # Chercher SKC, CLR, NSC, NCD
        if 'SKC' in metar_upper:
            print("NUAGES : SKC (Sky Clear - Ciel clair)")
            print()
        elif 'CLR' in metar_upper:
            print("NUAGES : CLR (Clear - Pas de nuages détectés)")
            print()
        elif 'NSC' in metar_upper:
            print("NUAGES : NSC (No Significant Cloud - Pas de nuages significatifs)")
            print()
        elif 'NCD' in metar_upper:
            print("NUAGES : NCD (No Cloud Detected - Pas de nuages détectés)")
            print()
    
    # Température et point de rosée
    temp_match = re.search(r'\b(M?\d{2})/(M?\d{2})\b', metar_upper)
    if temp_match:
        temp_str = temp_match.group(1)
        dewpoint_str = temp_match.group(2)
        
        temp = int(temp_str.replace('M', '-'))
        dewpoint = int(dewpoint_str.replace('M', '-'))
        spread = temp - dewpoint
        
        print("TEMPERATURE ET POINT DE ROSEE :")
        print(f"   Code : {temp_str}/{dewpoint_str}")
        print(f"   Température : {temp}°C ({temp * 9/5 + 32:.0f}°F)")
        print(f"   Point de rosée : {dewpoint}°C ({dewpoint * 9/5 + 32:.0f}°F)")
        print(f"   Écart (spread) : {spread}°C")
        
        if spread < 2:
            print("      ATTENTION : Écart très faible - Brouillard ou nuages bas imminents")
        elif spread < 5:
            print("      Humidité élevée - Surveillez la formation de brouillard/nuages")
        else:
            print("      Écart confortable - Risque de brouillard faible")
        
        print()
    
    # Pression (QNH)
    pressure_match = re.search(r'\bQ(\d{4})\b', metar_upper)
    if pressure_match:
        qnh = int(pressure_match.group(1))
        inches = qnh * 0.02953
        
        print("PRESSION ATMOSPHERIQUE (QNH) :")
        print(f"   Code : Q{qnh}")
        print(f"   Valeur : {qnh} hPa (hectopascals)")
        print(f"   Équivalent : {inches:.2f} inHg (pouces de mercure)")
        
        if qnh > 1030:
            print("      Haute pression - Temps généralement stable et beau")
        elif qnh > 1013:
            print("      Pression légèrement élevée - Temps stable")
        elif qnh > 1000:
            print("      Pression normale à basse")
        else:
            print("      Basse pression - Temps instable, perturbations possibles")
        
        print()
    
    # Remarques (RMK section si présente)
    if 'RMK' in metar_upper:
        rmk_match = re.search(r'RMK\s+(.+)$', metar_upper)
        if rmk_match:
            remarks = rmk_match.group(1)
            print("REMARQUES (RMK) :")
            print(f"   {remarks}")
            print("   (Informations supplémentaires non standard)")
            print()


def get_wind_direction_name(direction: str) -> str:
    """Convert wind direction in degrees to cardinal direction name."""
    if direction == 'VRB':
        return 'Variable'
    
    deg = int(direction)
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    idx = round(deg / 22.5) % 16
    return directions[idx]


def describe_taf(taf: str) -> None:
    """Décrit les prévisions TAF en français avec décodage détaillé de chaque période."""
    taf_upper = taf.upper()
    
    # Extraire l'ICAO et l'heure d'émission
    icao_time_match = re.search(r'\b([A-Z]{4})\s+(\d{6})Z\s+(\d{4})/(\d{4})\b', taf_upper)
    if icao_time_match:
        icao = icao_time_match.group(1)
        issue_time = icao_time_match.group(2)
        valid_from = icao_time_match.group(3)
        valid_to = icao_time_match.group(4)
        
        issue_day = issue_time[:2]
        issue_hour = issue_time[2:4]
        issue_min = issue_time[4:6]
        
        day_from = valid_from[:2]
        hour_from = valid_from[2:]
        day_to = valid_to[:2]
        hour_to = valid_to[2:]
        
        print("EN-TETE DU TAF :")
        print(f"   Code OACI : {icao}")
        print(f"   Émis le : Jour {issue_day} à {issue_hour}:{issue_min} UTC")
        print(f"   Période de validité : Du jour {day_from} à {hour_from}:00Z au jour {day_to} à {hour_to}:00Z")
        print(f"   Durée : {int(day_to) - int(day_from)} jour(s) et {int(hour_to) - int(hour_from)} heures")
        print()
    
    # Découper le TAF en périodes (ligne de base, TEMPO, BECMG, FM, PROB)
    # Extraire la période de base (après la validité, avant le premier modificateur)
    base_match = re.search(r'(\d{4}/\d{4})\s+([^\s]+.*?)(?=\s+(?:TEMPO|BECMG|FM|PROB\d+)|$)', taf_upper, re.DOTALL)
    
    if base_match:
        base_period = base_match.group(2).strip()
        print("=" * 80)
        print("PERIODE DE BASE (conditions prévues principales)")
        print("=" * 80)
        decode_taf_period(base_period, "Base")
        print()
    
    # Trouver tous les groupes TEMPO
    tempo_pattern = r'TEMPO\s+(\d{4})/(\d{4})\s+([^\s]+.*?)(?=\s+(?:TEMPO|BECMG|FM|PROB\d+)|$)'
    tempo_matches = re.finditer(tempo_pattern, taf_upper, re.DOTALL)
    
    for i, match in enumerate(tempo_matches, 1):
        from_time = match.group(1)
        to_time = match.group(2)
        conditions = match.group(3).strip()
        
        day_from = from_time[:2]
        hour_from = from_time[2:]
        day_to = to_time[:2]
        hour_to = to_time[2:]
        
        print("=" * 80)
        print(f"TEMPO {i} - Changements TEMPORAIRES (fluctuations < 1 heure)")
        print("=" * 80)
        print(f"Période : Du jour {day_from} à {hour_from}:00Z au jour {day_to} à {hour_to}:00Z")
        print("Signification : Conditions temporaires, revenant aux conditions de base")
        print()
        decode_taf_period(conditions, f"TEMPO {i}")
        print()
    
    # Trouver tous les groupes BECMG
    becmg_pattern = r'BECMG\s+(\d{4})/(\d{4})\s+([^\s]+.*?)(?=\s+(?:TEMPO|BECMG|FM|PROB\d+)|$)'
    becmg_matches = re.finditer(becmg_pattern, taf_upper, re.DOTALL)
    
    for i, match in enumerate(becmg_matches, 1):
        from_time = match.group(1)
        to_time = match.group(2)
        conditions = match.group(3).strip()
        
        day_from = from_time[:2]
        hour_from = from_time[2:]
        day_to = to_time[:2]
        hour_to = to_time[2:]
        
        print("=" * 80)
        print(f"BECMG {i} - EVOLUTION graduelle (changement permanent)")
        print("=" * 80)
        print(f"Période de transition : Du jour {day_from} à {hour_from}:00Z au jour {day_to} à {hour_to}:00Z")
        print("Signification : Changement progressif vers les nouvelles conditions")
        print()
        decode_taf_period(conditions, f"BECMG {i}")
        print()
    
    # Trouver tous les groupes FM (FROM)
    fm_pattern = r'FM(\d{6})\s+([^\s]+.*?)(?=\s+(?:TEMPO|BECMG|FM\d{6}|PROB\d+)|$)'
    fm_matches = re.finditer(fm_pattern, taf_upper, re.DOTALL)
    
    for i, match in enumerate(fm_matches, 1):
        from_time = match.group(1)
        conditions = match.group(2).strip()
        
        day = from_time[:2]
        hour = from_time[2:4]
        minute = from_time[4:6]
        
        print("=" * 80)
        print(f"FM {i} - Changement À PARTIR DE (permanent et rapide)")
        print("=" * 80)
        print(f"À partir de : Jour {day} à {hour}:{minute} UTC")
        print("Signification : Changement rapide et permanent des conditions")
        print()
        decode_taf_period(conditions, f"FM {i}")
        print()
    
    # Trouver tous les groupes PROB (probabilité)
    prob_pattern = r'PROB(\d+)\s+(?:TEMPO\s+)?(\d{4})/(\d{4})\s+([^\s]+.*?)(?=\s+(?:TEMPO|BECMG|FM|PROB\d+)|$)'
    prob_matches = re.finditer(prob_pattern, taf_upper, re.DOTALL)
    
    for i, match in enumerate(prob_matches, 1):
        probability = match.group(1)
        from_time = match.group(2)
        to_time = match.group(3)
        conditions = match.group(4).strip()
        
        day_from = from_time[:2]
        hour_from = from_time[2:]
        day_to = to_time[:2]
        hour_to = to_time[2:]
        
        print("=" * 80)
        print(f"PROB{probability} {i} - Probabilité {probability}% de conditions particulières")
        print("=" * 80)
        print(f"Période : Du jour {day_from} à {hour_from}:00Z au jour {day_to} à {hour_to}:00Z")
        if 'TEMPO' in match.group(0):
            print("Type : PROB TEMPO (temporaire)")
        print()
        decode_taf_period(conditions, f"PROB{probability} {i}")
        print()


def decode_taf_period(conditions: str, period_name: str) -> None:
    """Décode une période spécifique du TAF."""
    conditions_upper = conditions.upper()
    
    # Vent
    wind_match = re.search(r'\b(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT\b', conditions_upper)
    if wind_match:
        direction = wind_match.group(1)
        speed = int(wind_match.group(2))
        gust = int(wind_match.group(3)) if wind_match.group(3) else None
        
        print("VENT prévu :")
        if direction == "VRB":
            print(f"   {direction}{speed}{'G' + str(gust) if gust else ''}KT")
            print(f"   Direction : VRB (Variable)")
        else:
            dir_name = get_wind_direction_name(direction)
            print(f"   {wind_match.group(0)}")
            print(f"   Direction : {direction}° (depuis le {dir_name})")
        
        print(f"   Vitesse : {speed} nœuds = {int(speed * 1.852)} km/h")
        
        if gust:
            print(f"   Rafales : Jusqu'à {gust} nœuds ({int(gust * 1.852)} km/h)")
            if gust > 25:
                print("      ATTENTION : Fortes rafales prévues !")
    
    # CAVOK
    if 'CAVOK' in conditions_upper:
        print("\nVISIBILITE et NUAGES :")
        print("   CAVOK - Excellentes conditions")
        print("   - Visibilité >= 10 km")
        print("   - Pas de nuages < 5000 ft")
        print("   - Pas de CB")
        print("   - Pas de météo significative")
        return
    
    # Visibilité
    vis_match = re.search(r'\b(\d{4})\b', conditions_upper)
    if vis_match:
        vis_meters = int(vis_match.group(1))
        print(f"\nVISIBILITE prévue :")
        print(f"   {vis_meters} mètres")
        
        if vis_meters == 9999:
            print(f"   = 10+ km (excellente)")
        else:
            vis_km = vis_meters / 1000
            print(f"   = {vis_km:.1f} km")
            if vis_meters < 1000:
                print("      ATTENTION : Très mauvaise visibilité !")
            elif vis_meters < 5000:
                print("      ATTENTION : Visibilité réduite")
    
    # Phénomènes météo
    weather_codes = []
    
    # Liste des codes météo à rechercher
    wx_codes = ['TSRA', 'TS', '+RA', '-RA', 'RA', '+SN', '-SN', 'SN', 'SHRA', 'SHSN', 
                'FG', 'BR', 'HZ', 'FU', 'DZ', 'GR', 'GS', 'FZRA', 'FZDZ']
    
    for wx_code in wx_codes:
        if wx_code in conditions_upper:
            weather_codes.append(wx_code)
    
    if weather_codes:
        print("\nPHENOMENES METEOROLOGIQUES prévus :")
        
        wx_descriptions = {
            'TSRA': 'TSRA - Orage avec pluie',
            'TS': 'TS - Orage',
            '+RA': '+RA - Pluie forte',
            '-RA': '-RA - Pluie faible',
            'RA': 'RA - Pluie modérée',
            '+SN': '+SN - Neige forte',
            '-SN': '-SN - Neige faible',
            'SN': 'SN - Neige modérée',
            'SHRA': 'SHRA - Averses de pluie',
            'SHSN': 'SHSN - Averses de neige',
            'FG': 'FG - Brouillard (visibilité < 1000m)',
            'BR': 'BR - Brume (visibilité 1000-5000m)',
            'HZ': 'HZ - Brume sèche',
            'FU': 'FU - Fumée',
            'DZ': 'DZ - Bruine',
            'GR': 'GR - Grêle',
            'GS': 'GS - Petite grêle',
            'FZRA': 'FZRA - Pluie se congelant',
            'FZDZ': 'FZDZ - Bruine se congelant'
        }
        
        for wx_code in weather_codes:
            desc = wx_descriptions.get(wx_code, wx_code)
            print(f"   {desc}")
            
            if 'TS' in wx_code:
                print("      ATTENTION : Orages - Éviter le vol !")
            if 'FZ' in wx_code:
                print("      ATTENTION : Givrage possible")
            if wx_code in ['+RA', '+SN']:
                print("      ATTENTION : Précipitations fortes")
    
    # Nuages
    cloud_pattern = re.compile(r'\b(FEW|SCT|BKN|OVC|VV)(\d{3})(CB|TCU)?\b')
    cloud_matches = list(cloud_pattern.finditer(conditions_upper))
    
    if cloud_matches:
        print("\nNUAGES prévus :")
        
        coverage_map = {
            'FEW': 'Quelques nuages (1-2 octas)',
            'SCT': 'Épars (3-4 octas)',
            'BKN': 'Fragmenté (5-7 octas)',
            'OVC': 'Couvert (8 octas)',
            'VV': 'Ciel invisible'
        }
        
        for i, match in enumerate(cloud_matches, 1):
            coverage = match.group(1)
            height_code = match.group(2)
            cloud_type = match.group(3) or ''
            
            height_ft = int(height_code) * 100
            height_m = int(height_ft * 0.3048)
            
            print(f"   {match.group(0)} : {coverage_map.get(coverage)} à {height_ft} ft ({height_m} m)")
            
            if cloud_type == 'CB':
                print("      CB - Cumulonimbus (orages) - DANGER !")
            elif cloud_type == 'TCU':
                print("      TCU - Cumulus bourgeonnant - Turbulence probable")
    elif 'NSC' in conditions_upper:
        print("\nNUAGES : NSC (Pas de nuages significatifs)")
    elif 'SKC' in conditions_upper:
        print("\nNUAGES : SKC (Ciel clair)")


def interactive_detail_viewer(weather_data: list[Weather], airports: list[Airport]) -> None:
    """Interactive prompt to view detailed conditions for specific airports."""
    airport_map = {a.icao: a for a in airports}
    
    while True:
        print()
        icao_input = input("Entrez le code ICAO pour voir les conditions détaillées (ou Entrée pour quitter) : ").strip().upper()
        
        if not icao_input:
            print("\nAu revoir !")
            break
        
        # Find the weather data for this ICAO
        weather = next((w for w in weather_data if w.icao == icao_input), None)
        
        if not weather:
            print(f"  Aéroport '{icao_input}' non trouvé dans la liste des aéroports bretons.")
            available = [w.icao for w in weather_data if w.metar_raw][:10]
            if available:
                print(f"  Disponibles (avec données) : {', '.join(available)}...")
            continue
        
        # Find the airport info
        airport = airport_map.get(icao_input)
        
        print()
        print("=" * 100)
        print(f"CONDITIONS DÉTAILLÉES POUR {icao_input}")
        if airport:
            print(f"Aéroport : {airport.name}")
            print(f"Localisation : {airport.lat:.4f}N, {airport.lon:.4f}E")
        print("=" * 100)
        print()
        
        if not weather.metar_raw:
            print("Aucune donnée METAR disponible pour cet aéroport.")
            print()
            continue
        
        # Display full METAR
        print("METAR (Observation Météo Actuelle) :")
        print("-" * 100)
        print(weather.metar_raw)
        print("-" * 100)
        print()
        
        # Plain French description
        print("CONDITIONS :")
        print("-" * 100)
        describe_conditions(weather.metar_raw, weather.flight_category, weather.visibility_sm, weather.ceiling_ft)
        print("-" * 100)
        print()
        
        # Display full TAF if available
        if weather.taf_raw:
            print("TAF (Prévision d'Aérodrome) :")
            print("-" * 100)
            print(weather.taf_raw)
            print("-" * 100)
            print()
            print("RÉSUMÉ DES PRÉVISIONS :")
            print("-" * 100)
            describe_taf(weather.taf_raw)
            print("-" * 100)
        else:
            print("Aucun TAF (prévision) disponible pour cet aéroport.")
        
        print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fetch and rank Brittany airports by VFR conditions")
    parser.add_argument('--report-id', type=str, help='Use saved report ID (e.g., 3548536)')
    args = parser.parse_args()
    
    print("="*80)
    print("Brittany VFR METAR/TAF Ranker")
    print("="*80)
    
    # Load Brittany airports
    airports = load_brittany_airports()
    if not airports:
        print("No airports found in Brittany. Check filter criteria.")
        return 1
    
    # Get credentials
    username, password = get_credentials()
    
    # Create session and login
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Brittany-VFR-Checker/1.0'
    })
    
    if not login_meteo_fr(session, username, password):
        print("Failed to authenticate. Please check credentials and try again.")
        return 1
    
    # Fetch weather data
    weather_data = fetch_all_weather(session, airports, args.report_id)
    
    # Display ranked table
    display_ranked_table(weather_data, airports)
    
    # Interactive detail viewer
    interactive_detail_viewer(weather_data, airports)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
