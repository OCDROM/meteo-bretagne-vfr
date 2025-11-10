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
import re
from datetime import datetime

# Importer les fonctions du script METAR.py existant
from METAR import (
    load_brittany_airports,
    get_credentials,
    login_meteo_fr,
    fetch_all_weather,
    parse_taf_timeline,
    parse_metar_vfr,
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
        
        # Parser le TAF pour créer la timeline
        taf_timeline = parse_taf_timeline(weather.taf_raw) if weather.taf_raw else []
        
        return render_template('detail.html',
                             airport=airport,
                             weather=weather,
                             taf_timeline=taf_timeline,
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


@app.route('/decode/<icao>')
def decode(icao):
    """Page de décodage détaillé METAR en français."""
    try:
        icao = icao.upper()
        weather_data, airports = get_weather_data()
        
        airport = next((a for a in airports if a.icao == icao), None)
        weather = next((w for w in weather_data if w.icao == icao), None)
        
        if not airport or not weather or not weather.metar_raw:
            return render_template('error.html', 
                                 error=f"Données METAR non disponibles pour {icao}"), 404
        
        # Décoder tous les éléments du METAR
        decoded = decode_metar_detailed(weather.metar_raw)
        
        return render_template('decode.html',
                             airport=airport,
                             weather=weather,
                             decoded=decoded)
    
    except Exception as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/decode_taf/<icao>')
def decode_taf(icao):
    """Page de décodage détaillé TAF en français."""
    try:
        icao = icao.upper()
        weather_data, airports = get_weather_data()
        
        airport = next((a for a in airports if a.icao == icao), None)
        weather = next((w for w in weather_data if w.icao == icao), None)
        
        if not airport or not weather or not weather.taf_raw:
            return render_template('error.html', 
                                 error=f"Données TAF non disponibles pour {icao}"), 404
        
        # Décoder tous les éléments du TAF
        decoded = decode_taf_detailed(weather.taf_raw)
        
        return render_template('decode_taf.html',
                             airport=airport,
                             weather=weather,
                             decoded=decoded)
    
    except Exception as e:
        return render_template('error.html', error=str(e)), 500


def decode_metar_detailed(metar: str) -> dict:
    """Décode un METAR avec tous les détails en français."""
    metar_upper = metar.upper()
    decoded = {}
    
    # ICAO et heure d'observation
    icao_time = re.search(r'\b([A-Z]{4})\s+(\d{6})Z\b', metar_upper)
    if icao_time:
        decoded['icao'] = icao_time.group(1)
        time_str = icao_time.group(2)
        decoded['day'] = time_str[:2]
        decoded['hour'] = time_str[2:4]
        decoded['minute'] = time_str[4:6]
        decoded['observation_time'] = f"{time_str[:2]} à {time_str[2:4]}:{time_str[4:6]} UTC"
    
    # Période de validité pour TAF (si présent)
    valid_match = re.search(r'\b(\d{6})Z\s+(\d{4})/(\d{4})\b', metar_upper)
    if valid_match:
        valid_from = valid_match.group(2)
        valid_to = valid_match.group(3)
        decoded['valid_from'] = f"{valid_from[:2]} à {valid_from[2:]}:00 UTC"
        decoded['valid_to'] = f"{valid_to[:2]} à {valid_to[2:]}:00 UTC"
        decoded['valid_period'] = f"Du {valid_from[:2]} à {valid_from[2:]}h au {valid_to[:2]} à {valid_to[2:]}h UTC"
    
    # AUTO
    decoded['auto'] = 'AUTO' in metar_upper
    
    # Vent - aplatir la structure
    wind_match = re.search(r'\b(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT\b', metar_upper)
    if wind_match:
        decoded['wind_dir'] = wind_match.group(1)
        decoded['wind_speed'] = int(wind_match.group(2))
        decoded['wind_gust'] = int(wind_match.group(3)) if wind_match.group(3) else None
    
    # Variation vent
    wind_var = re.search(r'\b(\d{3})V(\d{3})\b', metar_upper)
    if wind_var:
        decoded['wind_var'] = f"{wind_var.group(1)}V{wind_var.group(2)}"
    
    # Visibilité
    decoded['cavok'] = 'CAVOK' in metar_upper
    if not decoded['cavok']:
        vis_match = re.search(r'\b(\d{4})\b', metar_upper)
        if vis_match:
            decoded['visibility'] = int(vis_match.group(1))
    
    # Phénomènes météo
    phenomena = []
    for code in ['TSRA', 'TS', '+RA', '-RA', 'RA', 'SHRA', 'SN', 'FG', 'BR', 'DZ', 'GR', 'FZRA']:
        if code in metar_upper:
            phenomena.append(code)
    decoded['phenomena'] = phenomena
    
    # Nuages
    clouds = []
    cloud_pattern = re.compile(r'\b(FEW|SCT|BKN|OVC)(\d{3})(CB|TCU)?\b')
    for match in cloud_pattern.finditer(metar_upper):
        clouds.append({
            'coverage': match.group(1),
            'height': int(match.group(2)) * 100,
            'type': match.group(3) or None
        })
    decoded['clouds'] = clouds
    
    # Température - aplatir la structure
    temp_match = re.search(r'\b(M?\d{2})/(M?\d{2})\b', metar_upper)
    if temp_match:
        temp_str = temp_match.group(1).replace('M', '-')
        dew_str = temp_match.group(2).replace('M', '-')
        temp_val = int(temp_str)
        dew_val = int(dew_str)
        decoded['temperature'] = temp_val
        decoded['dewpoint'] = dew_val
        decoded['spread'] = temp_val - dew_val
    
    # Pression
    pressure_match = re.search(r'\bQ(\d{4})\b', metar_upper)
    if pressure_match:
        decoded['qnh'] = int(pressure_match.group(1))
    
    return decoded


def decode_taf_detailed(taf: str) -> dict:
    """Décode un TAF avec toutes les périodes et changements en français."""
    taf_upper = taf.upper()
    decoded = {
        'periods': [],
        'tempo_periods': [],
        'becmg_periods': [],
        'prob_periods': []
    }
    
    # ICAO et heure d'émission
    icao_time = re.search(r'\b([A-Z]{4})\s+(\d{6})Z\b', taf_upper)
    if icao_time:
        decoded['icao'] = icao_time.group(1)
        time_str = icao_time.group(2)
        decoded['issue_day'] = time_str[:2]
        decoded['issue_hour'] = time_str[2:4]
        decoded['issue_minute'] = time_str[4:6]
        decoded['issue_time'] = f"{time_str[:2]} à {time_str[2:4]}:{time_str[4:6]} UTC"
    
    # Période de validité
    valid_match = re.search(r'\b(\d{6})Z\s+(\d{4})/(\d{4})\b', taf_upper)
    if valid_match:
        valid_from = valid_match.group(2)
        valid_to = valid_match.group(3)
        decoded['valid_from_day'] = valid_from[:2]
        decoded['valid_from_hour'] = valid_from[2:]
        decoded['valid_to_day'] = valid_to[:2]
        decoded['valid_to_hour'] = valid_to[2:]
        decoded['valid_period'] = f"Du {valid_from[:2]} à {valid_from[2:]}h au {valid_to[:2]} à {valid_to[2:]}h UTC"
    
    # Période de base (après la validité jusqu'au premier modificateur)
    base_match = re.search(r'(\d{4}/\d{4})\s+(.*?)(?=\s+(?:TEMPO|BECMG|FM|PROB\d+)|$)', taf_upper, re.DOTALL)
    if base_match:
        base_conditions = base_match.group(2).strip()
        decoded['base_conditions'] = parse_taf_conditions(base_conditions)
        decoded['base_conditions']['period'] = base_match.group(1)
    
    # TEMPO (conditions temporaires)
    tempo_pattern = r'TEMPO\s+(\d{4}/\d{4})\s+(.*?)(?=\s+(?:TEMPO|BECMG|FM|PROB\d+)|$)'
    for match in re.finditer(tempo_pattern, taf_upper, re.DOTALL):
        period = match.group(1)
        conditions = match.group(2).strip()
        tempo_data = parse_taf_conditions(conditions)
        tempo_data['period'] = period
        tempo_data['from'] = f"{period[:2]} à {period[2:4]}h"
        tempo_data['to'] = f"{period[5:7]} à {period[7:]}h"
        decoded['tempo_periods'].append(tempo_data)
    
    # BECMG (changement progressif)
    becmg_pattern = r'BECMG\s+(\d{4}/\d{4})\s+(.*?)(?=\s+(?:TEMPO|BECMG|FM|PROB\d+)|$)'
    for match in re.finditer(becmg_pattern, taf_upper, re.DOTALL):
        period = match.group(1)
        conditions = match.group(2).strip()
        becmg_data = parse_taf_conditions(conditions)
        becmg_data['period'] = period
        becmg_data['from'] = f"{period[:2]} à {period[2:4]}h"
        becmg_data['to'] = f"{period[5:7]} à {period[7:]}h"
        decoded['becmg_periods'].append(becmg_data)
    
    # PROB (probabilité)
    prob_pattern = r'PROB(\d+)\s+(?:TEMPO\s+)?(\d{4}/\d{4})\s+(.*?)(?=\s+(?:TEMPO|BECMG|FM|PROB\d+)|$)'
    for match in re.finditer(prob_pattern, taf_upper, re.DOTALL):
        probability = match.group(1)
        period = match.group(2)
        conditions = match.group(3).strip()
        prob_data = parse_taf_conditions(conditions)
        prob_data['period'] = period
        prob_data['probability'] = probability
        prob_data['from'] = f"{period[:2]} à {period[2:4]}h"
        prob_data['to'] = f"{period[5:7]} à {period[7:]}h"
        decoded['prob_periods'].append(prob_data)
    
    return decoded


def parse_taf_conditions(conditions: str) -> dict:
    """Parse les conditions d'une période TAF."""
    parsed = {}
    conditions_upper = conditions.upper()
    
    # CAVOK
    parsed['cavok'] = 'CAVOK' in conditions_upper
    
    # Vent
    wind_match = re.search(r'\b(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT\b', conditions_upper)
    if wind_match:
        parsed['wind_dir'] = wind_match.group(1)
        parsed['wind_speed'] = int(wind_match.group(2))
        parsed['wind_gust'] = int(wind_match.group(3)) if wind_match.group(3) else None
    
    # Visibilité
    if not parsed['cavok']:
        vis_match = re.search(r'\b(\d{4})\b', conditions_upper)
        if vis_match:
            parsed['visibility'] = int(vis_match.group(1))
    
    # Phénomènes météo
    phenomena = []
    for code in ['TSRA', 'TS', '+RA', '-RA', 'RA', 'SHRA', 'SN', 'FG', 'BR', 'DZ', 'GR', 'FZRA', '+SHRA', '-SHRA']:
        if code in conditions_upper:
            phenomena.append(code)
    parsed['phenomena'] = phenomena
    
    # Nuages
    clouds = []
    cloud_pattern = re.compile(r'\b(FEW|SCT|BKN|OVC)(\d{3})(CB|TCU)?\b')
    for match in cloud_pattern.finditer(conditions_upper):
        clouds.append({
            'coverage': match.group(1),
            'height': int(match.group(2)) * 100,
            'type': match.group(3) or None
        })
    parsed['clouds'] = clouds
    
    return parsed


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
