#!/usr/bin/env python3
"""Test web_app.py get_weather_data()"""

import os
import sys

# Définir les variables d'environnement pour le test
os.environ['METEO_USER'] = 'RMQR'
os.environ['METEO_PASS'] = 'Njord562026'

sys.path.insert(0, os.path.dirname(__file__))

# Import après avoir défini les variables d'environnement
from web_app import get_weather_data

print("=== Test de get_weather_data() ===\n")

try:
    weather_data, airports = get_weather_data(force_refresh=True)
    
    print(f"✓ Données récupérées:")
    print(f"  - {len(airports)} aéroports")
    print(f"  - {len(weather_data)} données météo")
    
    with_data = sum(1 for w in weather_data if w.metar_raw or w.taf_raw)
    print(f"  - {with_data} aéroports avec données\n")
    
    print("=== Premiers aéroports ===")
    for w in weather_data[:5]:
        airport = next((a for a in airports if a.icao == w.icao), None)
        print(f"\n{w.icao} - {airport.name if airport else 'Unknown'}")
        print(f"  METAR: {'Oui' if w.metar_raw else 'Non'}")
        print(f"  TAF: {'Oui' if w.taf_raw else 'Non'}")
        print(f"  Catégorie: {w.flight_category}")
        print(f"  Score VFR: {w.vfr_score}")
        
except Exception as e:
    print(f"✗ Erreur: {e}")
    import traceback
    traceback.print_exc()
