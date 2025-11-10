#!/usr/bin/env python3
"""
Minimal, zero-dependency script to fetch METAR and TAF from NOAA ADDS
and print a short decoded summary for a given ICAO station.

This keeps everything free (NOAA ADDS is public) and requires only Python
standard library. Use this as a starting point for a VFR situational app.
"""
from __future__ import annotations

import argparse
import math
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import re
import os
from datetime import datetime


# Regex for a valid 4-letter ICAO identifier (e.g., LFPG, EGLL)
ICAO_RE = re.compile(r'^[A-Z]{4}$')


ADDS_BASE = "https://aviationweather.gov/adds/dataserver_current/httpparam"

# OurAirports free CSV (used to locate nearby aerodromes)
OURAIRPORTS_URL = "https://ourairports.com/data/airports.csv"
AIRPORTS_CACHE = "airports.csv"

# Small builtin mapping for commonly used fields (fast, authoritative fallback)
# Add more as needed. Format: ICAO: (name, lat, lon)
BUILTIN_AIRPORTS = {
    # LFED - Centre Bretagne Aerodrome (approx coords)
    'LFED': {'name': 'Centre Bretagne', 'lat': 48.1333, 'lon': -3.4083},
    # Add other frequently used fields here if desired
}


def dms_to_decimal(deg: float, minutes: float, seconds: float, hemi: str) -> float:
    dec = float(deg) + float(minutes) / 60.0 + float(seconds) / 3600.0
    if hemi.upper() in ('S', 'W'):
        dec = -dec
    return dec


def parse_dms_string(s: str) -> tuple[float, float] | None:
    # Try to find two DMS occurrences and convert to decimal
    # Accept formats like 48°07'59"N 003°24'30"W or 48 07 59 N 003 24 30 W
    dms_re = re.compile(r"(\d{1,3})[^0-9A-Za-z]{0,3}(\d{1,2})[^0-9A-Za-z]{0,3}(\d{1,2}(?:\.\d+)?)\s*([NSEW])", re.I)
    parts = dms_re.findall(s)
    if len(parts) >= 2:
        latp = parts[0]
        lonp = parts[1]
        lat = dms_to_decimal(latp[0], latp[1], latp[2], latp[3])
        lon = dms_to_decimal(lonp[0], lonp[1], lonp[2], lonp[3])
        return (lat, lon)
    return None


def parse_decimal_pair(s: str) -> tuple[float, float] | None:
    # find two decimal numbers close together and plausibly within France bounds
    dec_re = re.compile(r"([-+]?[0-9]*\.?[0-9]+)\s*[,;\s]\s*([-+]?[0-9]*\.?[0-9]+)")
    for m in dec_re.finditer(s):
        a = float(m.group(1))
        b = float(m.group(2))
        # determine lat/lon order by plausible lat range
        if 40.0 <= a <= 52.0 and -10.0 <= b <= 10.0:
            return (a, b)
        if 40.0 <= b <= 52.0 and -10.0 <= a <= 10.0:
            return (b, a)
    return None


def sia_lookup_coords(icao: str) -> tuple[float, float] | None:
    """Best-effort lookup of aerodrome coords from SIA web pages (returns lat, lon).

    This tries a couple of known URL patterns and parses the HTML for DMS or decimal coords.
    It's a fallback and may fail for some pages — then returns None.
    """
    icao = icao.upper()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Python-SIA-Client/1.0'}
    patterns = [
        f"https://www.sia.aviation-civile.gouv.fr/aip/eAIP/FR-AD-2.{icao}-fr-FR.html",
        f"https://www.sia.aviation-civile.gouv.fr/dvd/eAIP/FR-AD-2.{icao}-fr-FR.html",
    ]
    for url in patterns:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                text = resp.read().decode('utf-8', errors='ignore')
        except Exception:
            continue
        # try decimal pair first
        dec = parse_decimal_pair(text)
        if dec:
            return dec
        # try DMS
        dms = parse_dms_string(text)
        if dms:
            return dms
    return None


def decode_metar_raw(raw: str) -> dict:
    """Lightweight METAR raw text decoder: extracts CAVOK, ceiling, RVR and cloud summary.

    Not a full METAR parser but useful for quick VFR checks.
    """
    out = {'cavok': False, 'ceiling_ft': None, 'clouds': None, 'rvr': None}
    if not raw:
        return out
    raw = raw.upper()
    if 'CAVOK' in raw:
        out['cavok'] = True
        out['clouds'] = 'CAVOK'
        out['ceiling_ft'] = None
        return out
    # find cloud layers like BKN020, OVC010
    cloud_re = re.compile(r"(FEW|SCT|BKN|OVC)(\d{3})(CB|TCU)?")
    layers = cloud_re.findall(raw)
    if layers:
        out['clouds'] = ','.join([f"{l[0]}{l[1]}{l[2]}".strip() for l in layers])
        # ceiling is the lowest BKN or OVC
        for typ, h, _ in layers:
            if typ in ('BKN', 'OVC'):
                try:
                    out['ceiling_ft'] = int(h) * 100
                    break
                except Exception:
                    pass
    # RVR
    rvr_re = re.compile(r"R(\d{2,4})(L|R|C)?/([MP]?\d{4})(V[MP]?\d{4})?")
    rvrm = rvr_re.search(raw)
    if rvrm:
        out['rvr'] = rvrm.group(3)
    return out





def fetch_adds(data_source: str, params: dict) -> ET.Element:
    q = {"dataSource": data_source, "requestType": "retrieve", "format": "xml"}
    q.update(params)
    url = ADDS_BASE + "?" + urllib.parse.urlencode(q)
    # Use a friendly User-Agent to avoid simple bot blocking (some servers reject default Python UA)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Python-ADDS-Client/1.0',
        'Accept': 'application/xml, text/xml, */*',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read()
    root = ET.fromstring(body)
    return root


def get_metar(station: str, hours: int = 3) -> dict | None:
    try:
        root = fetch_adds("metars", {"stationString": station, "hoursBeforeNow": str(hours)})
        metars = root.findall('.//METAR')
        if metars:
            m = metars[0]
            return {
                "raw_text": (m.findtext("raw_text") or "").strip(),
                "station_id": m.findtext("station_id"),
                "observation_time": m.findtext("observation_time"),
                "temp_c": m.findtext("temp_c"),
                "dewpoint_c": m.findtext("dewpoint_c"),
                "visibility_statute_mi": m.findtext("visibility_statute_mi"),
                "wind_dir_degrees": m.findtext("wind_dir_degrees"),
                "wind_speed_kt": m.findtext("wind_speed_kt"),
                "wind_gust_kt": m.findtext("wind_gust_kt"),
                "flight_category": m.findtext("flight_category"),
            }
    except Exception as e:
        # Try a simple plaintext fallback (NOAA tgftp) when ADDS blocks us (403) or on other errors
        try:
            return fetch_metar_tgftp(station)
        except Exception:
            pass
    return None


def get_taf(station: str, hours: int = 6) -> dict | None:
    try:
        root = fetch_adds("tafs", {"stationString": station, "hoursBeforeNow": str(hours)})
        tafs = root.findall('.//TAF')
        if tafs:
            t = tafs[0]
            return {
                "raw_text": (t.findtext("raw_text") or "").strip(),
                "station_id": t.findtext("station_id"),
                "issue_time": t.findtext("issue_time"),
                "valid_time_from": t.findtext("valid_time_from"),
                "valid_time_to": t.findtext("valid_time_to"),
            }
    except Exception:
        # fallback to plain text TAF from NOAA tgftp
        try:
            return fetch_taf_tgftp(station)
        except Exception:
            pass
    return None


def fetch_metar_tgftp(station: str) -> dict | None:
    """Fetch raw METAR from NOAA tgftp text file as a fallback. Returns minimal dict or None."""
    url = f"https://tgftp.nws.noaa.gov/data/observations/metar/stations/{station.upper()}.TXT"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Python-METAR-Fallback/1.0'}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode('utf-8', errors='ignore').strip()
    if not body:
        return None
    # tgftp METAR usually contains a timestamp line then the METAR on the next line
    lines = [l for l in body.splitlines() if l.strip()]
    if len(lines) == 1:
        raw = lines[0].strip()
        obs = None
    else:
        # first line often like '2025-11-10 12:00:00'
        obs = lines[0].strip()
        raw = lines[1].strip()
    out = {"raw_text": raw, "station_id": station.upper(), "observation_time": obs}
    # Try to extract wind (e.g., 22015KT or VRB03KT or 18015G25KT)
    try:
        w = re.search(r"\b(VRB|\d{3})(\d{2,3})(G(\d{2,3}))?KT\b", raw)
        if w:
            wd = w.group(1)
            ws = w.group(2)
            gust = w.group(4)
            out['wind_dir_degrees'] = None if wd == 'VRB' else wd
            out['wind_speed_kt'] = ws
            if gust:
                out['wind_gust_kt'] = gust
    except Exception:
        pass
    # Temp/dew like 12/07 or M01/M02
    try:
        t = re.search(r"\b(M?\d{2})/(M?\d{2})\b", raw)
        if t:
            def conv(v: str) -> int:
                if v.startswith('M'):
                    return -int(v[1:])
                return int(v)
            out['temp_c'] = conv(t.group(1))
            out['dewpoint_c'] = conv(t.group(2))
    except Exception:
        pass
    # Visibility: look for meters (e.g., 9999) or SM (e.g., 10SM)
    try:
        m = re.search(r"\b(\d{4})\b", raw)
        if m:
            meters = int(m.group(1))
            miles = meters * 0.000621371
            out['visibility_statute_mi'] = f"{miles:.1f}"
        else:
            sm = re.search(r"\b(\d+(?:/\d+)?)SM\b", raw)
            if sm:
                out['visibility_statute_mi'] = sm.group(1)
    except Exception:
        pass
    return out


def fetch_taf_tgftp(station: str) -> dict | None:
    """Fetch raw TAF text from NOAA tgftp as a fallback."""
    url = f"https://tgftp.nws.noaa.gov/data/forecasts/taf/stations/{station.upper()}.TXT"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Python-TAF-Fallback/1.0'}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode('utf-8', errors='ignore').strip()
    if not body:
        return None
    return {"raw_text": body, "station_id": station.upper()}


def haversine_nm(lat1, lon1, lat2, lon2):
    # return nautical miles between two lat/lon points
    R_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    km = R_km * c
    nm = km * 0.539957
    return nm


def download_airports_csv(cache_path: str = AIRPORTS_CACHE) -> str:
    """Download the OurAirports airports.csv if not present and return path."""
    import os

    if os.path.exists(cache_path):
        return cache_path
    print(f"Downloading airports list from OurAirports to {cache_path} (one-time)...")
    with urllib.request.urlopen(OURAIRPORTS_URL, timeout=30) as resp:
        body = resp.read()
    with open(cache_path, "wb") as f:
        f.write(body)
    return cache_path


def load_airports(cache_path: str = AIRPORTS_CACHE) -> dict:
    """Load airports CSV and return mapping ICAO -> (name, lat, lon, country).

    Returns a mapping of the dataset 'ident' values (uppercased) to airport info.
    Filtering to only 4-letter ICAO codes is performed later when searching.
    """
    import csv

    path = download_airports_csv(cache_path)
    airports = {}
    with open(path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # OurAirports uses 'ident' for the ICAO/ident code; fallback to 'icao' if present
            icao = (row.get('ident') or row.get('icao') or '').strip()
            if not icao:
                continue
            try:
                lat = float(row.get('latitude_deg') or 0.0)
                lon = float(row.get('longitude_deg') or 0.0)
            except Exception:
                continue
            airports[icao.upper()] = {
                'name': row.get('name') or '',
                'lat': lat,
                'lon': lon,
                'country': row.get('iso_country') or '',
            }
    print(f"Loaded {len(airports)} airports from {path}")
    return airports


def find_nearby_airports(center_icao: str, radius_nm: float, airports: dict, max_results: int = 30) -> list:
    center = airports.get(center_icao.upper())
    if not center:
        return []
    res = []
    for icao, info in airports.items():
        dist = haversine_nm(center['lat'], center['lon'], info['lat'], info['lon'])
        if dist <= radius_nm:
            res.append((icao, info, dist))
    res.sort(key=lambda x: x[2])
    return res[:max_results]


def format_row(station, info, dist, metar, taf):
    name = (info.get('name') or '')[:24]
    dist_s = f"{dist:.0f}"
    met_time = metar.get('observation_time') if metar and metar.get('observation_time') else 'No METAR'
    vis = metar.get('visibility_statute_mi') if metar and metar.get('visibility_statute_mi') else '-'
    # decode raw METAR text for quick VFR cues
    metraw = metar.get('raw_text') if metar and metar.get('raw_text') else ''
    decoded = decode_metar_raw(metraw) if metraw else {}
    cavok = 'CAVOK' if decoded.get('cavok') else ''
    ceiling = f"{decoded.get('ceiling_ft') or ''}"
    wind = ''
    if metar and metar.get('wind_speed_kt') is not None:
        wd = metar.get('wind_dir_degrees') or 'VRB'
        ws = metar.get('wind_speed_kt') or '0'
        gust = metar.get('wind_gust_kt')
        wind = f"{wd}@{ws}"
        if gust:
            wind += f"G{gust}"
    temp = metar.get('temp_c') if metar and metar.get('temp_c') is not None else '-'
    cat = metar.get('flight_category') if metar and metar.get('flight_category') else '-'
    taf_one = ''
    if taf and taf.get('raw_text'):
        taf_one = taf.get('raw_text').splitlines()[0][:30]
    else:
        taf_one = 'No TAF'
    return f"{station:6} {name:24} {dist_s:4}nm  {met_time:19}  V:{vis:4}  W:{wind:8}  T:{temp:4}  {cat:3}  C:{ceiling:5} {cavok:5} TAF:{taf_one}"


def print_summary(metar: dict | None, taf: dict | None) -> None:
    print("--- Weather summary (source: NOAA ADDS) ---")
    if metar is None:
        print("No METAR available.")
    else:
        print(f"Station: {metar.get('station_id')}")
        print(f"Observed: {metar.get('observation_time')}")
        print(f"Raw: {metar.get('raw_text')}")
        print(f"Temp (C): {metar.get('temp_c')}")
        print(f"Dewpt (C): {metar.get('dewpoint_c')}")
        print(f"Visibility (mi): {metar.get('visibility_statute_mi')}")
        wd = metar.get('wind_dir_degrees') or 'VRB'
        ws = metar.get('wind_speed_kt') or '0'
        gust = metar.get('wind_gust_kt')
        windstr = f"{wd} @ {ws} kt"
        if gust:
            windstr += f" gust {gust} kt"
        print(f"Wind: {windstr}")
        print(f"Flight category: {metar.get('flight_category')}")

    if taf is None:
        print("No TAF available.")
    else:
        print("\n--- TAF ---")
        print(f"Issued: {taf.get('issue_time')}")
        print(f"Valid from: {taf.get('valid_time_from')} to {taf.get('valid_time_to')}")
        print(taf.get('raw_text'))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch METAR/TAF from NOAA ADDS (free)")
    p.add_argument("--station", "-s", default="LFED", help="ICAO station (default LFED)")
    p.add_argument("--metar-hours", type=int, default=3, help="hoursBeforeNow for METAR (default 3)")
    p.add_argument("--taf-hours", type=int, default=6, help="hoursBeforeNow for TAF (default 6)")
    p.add_argument("--radius-nm", type=float, default=100.0, help="search radius in nautical miles (default 100)")
    p.add_argument("--max-stations", type=int, default=20, help="max nearby stations to fetch (default 20)")
    p.add_argument("--lat", type=float, help="fallback latitude for center if ICAO unknown")
    p.add_argument("--lon", type=float, help="fallback longitude for center if ICAO unknown")
    p.add_argument("--include-non-icao", action="store_true", help="Include non-ICAO identifiers (e.g., FR-0050) in nearby search")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    # prompt for start ICAO (4 letters)
    while True:
        start = input("Enter start ICAO (4 letters) [default LFED]: ").strip().upper()
        if not start:
            start = args.station.upper()
        if ICAO_RE.match(start):
            break
        print("Please enter a valid 4-letter ICAO code (e.g. LFED, LFRN).")

    # Load airport locations (OurAirports free dataset)
    airports = load_airports()

    # Determine center coordinates (use airports, SIA or builtin fallbacks as before)
    center = start
    if center not in airports:
        print(f"Center {center} not in OurAirports; trying SIA lookup...")
        sia_coords = sia_lookup_coords(center)
        if sia_coords:
            airports_center = {'name': f'SIA {center}', 'lat': sia_coords[0], 'lon': sia_coords[1]}
            airports_tmp = dict(airports)
            airports_tmp['_CENTER_'] = airports_center
            initial_max = max(args.max_stations * 5, args.max_stations)
            nearby = find_nearby_airports('_CENTER_', args.radius_nm, airports_tmp, max_results=initial_max)
        elif center in BUILTIN_AIRPORTS:
            bc = BUILTIN_AIRPORTS[center]
            airports_center = {'name': bc['name'], 'lat': bc['lat'], 'lon': bc['lon']}
            airports_tmp = dict(airports)
            airports_tmp['_CENTER_'] = airports_center
            initial_max = max(args.max_stations * 5, args.max_stations)
            nearby = find_nearby_airports('_CENTER_', args.radius_nm, airports_tmp, max_results=initial_max)
        elif args.lat is not None and args.lon is not None:
            airports_center = {'name': f'coords {args.lat},{args.lon}', 'lat': args.lat, 'lon': args.lon}
            airports_tmp = dict(airports)
            airports_tmp['_CENTER_'] = airports_center
            initial_max = max(args.max_stations * 5, args.max_stations)
            nearby = find_nearby_airports('_CENTER_', args.radius_nm, airports_tmp, max_results=initial_max)
        else:
            print(f"Center station {center} not found in airports list and no coords provided. Using station directly for METAR/TAF fetch.")
            try:
                metar = get_metar(center, args.metar_hours)
            except Exception as e:
                print(f"Error fetching METAR: {e}")
                metar = None
            try:
                taf = get_taf(center, args.taf_hours)
            except Exception as e:
                print(f"Error fetching TAF: {e}")
                taf = None
            print_summary(metar, taf)
            return 0
    else:
        initial_max = max(args.max_stations * 5, args.max_stations)
        nearby = find_nearby_airports(center, args.radius_nm, airports, max_results=initial_max)

    # filter out the temporary center marker if present
    nearby = [t for t in nearby if t[0] != '_CENTER_']
    # By default, only include standard 4-letter ICAO idents
    if not args.include_non_icao:
        nearby = [(i,info,d) for (i,info,d) in nearby if ICAO_RE.match(i)]
    # Trim to the requested number of stations after filtering
    nearby = nearby[:args.max_stations]

    center_name = airports[center]['name'] if center in airports else (airports_tmp.get('_CENTER_', {}).get('name', center) if 'airports_tmp' in locals() else center)

    print(f"Found {len(nearby)} nearby stations within {args.radius_nm} nm of {center} ({center_name})")
    print("--- Nearby station table ---")
    print("ICAO   Name                      Dist  Obs Time             V   Wind      Temp  Cat   TAF snippet")
    for icao, info, dist in nearby:
        try:
            metar = get_metar(icao, args.metar_hours)
        except Exception:
            metar = None
        try:
            taf = get_taf(icao, args.taf_hours)
        except Exception:
            taf = None
        print(format_row(icao, info, dist, metar or {}, taf or {}))

    # Prompt for destination ICAO from the list and show full METAR/TAF
    valid_icaos = {i for (i, _, _) in nearby}
    dest = ''
    while True:
        dest = input("Enter destination ICAO from the list above (or blank to exit): ").strip().upper()
        if not dest:
            print("No destination entered. Exiting.")
            return 0
        if dest in valid_icaos:
            break
        print("Please enter one of the ICAO codes shown in the table.")

    print(f"Fetching full METAR/TAF for {dest}...")
    try:
        metar = get_metar(dest, args.metar_hours)
    except Exception as e:
        print(f"Error fetching METAR: {e}")
        metar = None
    try:
        taf = get_taf(dest, args.taf_hours)
    except Exception as e:
        print(f"Error fetching TAF: {e}")
        taf = None
    print_summary(metar, taf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

