#!/usr/bin/env python3
"""
Brittany VFR METAR/TAF - Application Web Flask

Application web pour consulter les conditions météo VFR des aéroports bretons.
Accessible depuis n'importe quel navigateur (ordinateur, téléphone, tablette).

Routes:
    / - Page d'accueil avec tableau des aéroports classés
    /detail/<icao> - Détails complets pour un aéroport spécifique
    /api/refresh - Rafraîchit les données météo

Usage local:
    python web_app.py
    Puis ouvrir http://localhost:5000 dans un navigateur
"""

from flask import Flask, render_template, jsonify, redirect, url_for
import os
import sys
from datetime import datetime

# Importer les fonctions du script METAR.py existant
from METAR import (
    load_brittany_airports,
    get_credentials,
    login_meteo_fr,
    fetch_all_weather,
    Airport,
    Weather
)
import requests

app = Flask(__name__)

# Cache global pour éviter de refaire les requêtes à chaque visite
weather_cache = {
    'data': None,
    'airports': None,
    'session': None,
    'last_update': None
}


def get_weather_data(force_refresh=False):
    """Récupère les données météo (avec cache)."""
    global weather_cache
    
    # Si cache valide (moins de 30 minutes), retourner le cache
    if not force_refresh and weather_cache['data'] is not None:
        if weather_cache['last_update']:
            elapsed = (datetime.now() - weather_cache['last_update']).total_seconds()
            if elapsed < 1800:  # 30 minutes
                return weather_cache['data'], weather_cache['airports']
    
    # Sinon, récupérer les nouvelles données
    try:
        # Charger les aéroports
        airports = load_brittany_airports()
        
        # Créer une session et se connecter
        if weather_cache['session'] is None:
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Brittany-VFR-Web/1.0'
            })
            
            # Récupérer les credentials
            username, password = get_credentials()
            
            # Login
            if not login_meteo_fr(session, username, password):
                raise Exception("Échec de l'authentification")
            
            weather_cache['session'] = session
        else:
            session = weather_cache['session']
        
        # Récupérer les données météo
        weather_data = fetch_all_weather(session, airports)
        
        # Mettre à jour le cache
        weather_cache['data'] = weather_data
        weather_cache['airports'] = airports
        weather_cache['last_update'] = datetime.now()
        
        return weather_data, airports
    
    except Exception as e:
        print(f"Erreur lors de la récupération des données: {e}")
        # Si erreur, retourner le cache même s'il est ancien
        if weather_cache['data']:
            return weather_cache['data'], weather_cache['airports']
        raise


@app.route('/')
def index():
    """Page d'accueil avec le tableau des aéroports classés."""
    try:
        weather_data, airports = get_weather_data()
        
        # Trier par VFR score
        sorted_weather = sorted(weather_data, key=lambda w: w.vfr_score, reverse=True)
        
        # Construire la map des aéroports
        airport_map = {a.icao: a for a in airports}
        
        # Préparer les données pour le template
        airports_with_weather = []
        for weather in sorted_weather:
            airport = airport_map.get(weather.icao)
            airports_with_weather.append({
                'weather': weather,
                'airport': airport
            })
        
        last_update = weather_cache['last_update']
        
        return render_template('index.html', 
                             airports=airports_with_weather,
                             last_update=last_update)
    
    except Exception as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/detail/<icao>')
def detail(icao):
    """Page de détails pour un aéroport spécifique."""
    try:
        icao = icao.upper()
        weather_data, airports = get_weather_data()
        
        # Trouver l'aéroport et ses données météo
        airport = next((a for a in airports if a.icao == icao), None)
        weather = next((w for w in weather_data if w.icao == icao), None)
        
        if not airport or not weather:
            return render_template('error.html', 
                                 error=f"Aéroport {icao} non trouvé"), 404
        
        return render_template('detail.html',
                             airport=airport,
                             weather=weather,
                             last_update=weather_cache['last_update'])
    
    except Exception as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/api/refresh')
def api_refresh():
    """API pour forcer le rafraîchissement des données."""
    try:
        weather_data, airports = get_weather_data(force_refresh=True)
        return jsonify({
            'status': 'success',
            'message': 'Données rafraîchies',
            'last_update': weather_cache['last_update'].isoformat(),
            'airports_count': len(airports)
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.template_filter('format_datetime')
def format_datetime(dt):
    """Formatte une date/heure pour l'affichage."""
    if dt:
        return dt.strftime('%d/%m/%Y %H:%M:%S')
    return 'N/A'


@app.template_filter('category_color')
def category_color(category):
    """Retourne une classe CSS selon la catégorie VFR."""
    colors = {
        'CAVOK': 'success',
        'VFR': 'primary',
        'MVFR': 'warning',
        'IFR': 'danger',
        'LIFR': 'dark'
    }
    return colors.get(category, 'secondary')


@app.template_filter('visibility_km')
def visibility_km(vis_sm):
    """Convertit la visibilité en km."""
    if vis_sm:
        km = vis_sm * 1.60934
        if km >= 9.9:
            return "10+ km"
        return f"{km:.1f} km"
    return "N/A"


if __name__ == '__main__':
    # En développement local
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
