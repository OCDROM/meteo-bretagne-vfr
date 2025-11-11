#!/usr/bin/env python3
"""Test rapide de récupération des données météo."""

import sys
import os

# Ajouter le répertoire au path
sys.path.insert(0, os.path.dirname(__file__))

from METAR import load_brittany_airports, login_meteo_fr, fetch_all_weather

def test_weather_fetch():
    """Test de récupération des données."""
    print("=== Test de récupération des données météo ===\n")
    
    # Credentials
    username = os.environ.get('METEO_USER', 'RMQR')
    password = os.environ.get('METEO_PASS', 'Njord562026')
    
    print(f"Username: {username}")
    print(f"Password: {'*' * len(password)}\n")
    
    # Charger les aéroports
    print("1. Chargement des aéroports...")
    try:
        airports = load_brittany_airports()
        print(f"   ✓ {len(airports)} aéroports chargés\n")
    except Exception as e:
        print(f"   ✗ Erreur: {e}\n")
        return
    
    # Se connecter
    print("2. Connexion à aviation.meteo.fr...")
    try:
        import requests
        session = requests.Session()
        login_success = login_meteo_fr(session, username, password)
        print(f"   ✓ Connecté (login success: {login_success})\n")
    except Exception as e:
        print(f"   ✗ Erreur de connexion: {e}\n")
        import traceback
        traceback.print_exc()
        return
    
    # Récupérer les données
    print("3. Récupération des données météo...")
    try:
        weather_data = fetch_all_weather(session, airports)
        print(f"   ✓ {len(weather_data)} aéroports traités\n")
        
        # Statistiques
        with_metar = sum(1 for w in weather_data if w.metar_raw)
        with_taf = sum(1 for w in weather_data if w.taf_raw)
        
        print("=== Statistiques ===")
        print(f"Aéroports avec METAR: {with_metar}/{len(weather_data)}")
        print(f"Aéroports avec TAF:   {with_taf}/{len(weather_data)}\n")
        
        # Afficher les 5 premiers résultats
        print("=== Premiers résultats ===")
        for i, w in enumerate(weather_data[:5], 1):
            print(f"\n{i}. {w.icao}:")
            if w.metar_raw:
                print(f"   METAR: {w.metar_raw[:70]}...")
            else:
                print(f"   METAR: Aucun")
            
            if w.taf_raw:
                print(f"   TAF:   {w.taf_raw[:70]}...")
            else:
                print(f"   TAF:   Aucun")
            
            print(f"   Catégorie VFR: {w.flight_category}")
            print(f"   Score: {w.vfr_score}")
        
        # Si aucune donnée METAR
        if with_metar == 0:
            print("\n⚠️  PROBLÈME: Aucun METAR récupéré!")
            print("Causes possibles:")
            print("  - Quota API dépassé")
            print("  - Credentials incorrects")
            print("  - Problème de connexion")
            print("  - Site aviation.meteo.fr en maintenance")
        
    except Exception as e:
        print(f"   ✗ Erreur: {e}\n")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_weather_fetch()
