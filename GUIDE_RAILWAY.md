# Guide de déploiement sur Railway.app

## Votre projet est prêt !

Les fichiers suivants ont été créés :
- ✅ `Procfile` - Commande de démarrage
- ✅ `runtime.txt` - Version Python
- ✅ `.gitignore` - Fichiers à exclure
- ✅ `requirements.txt` - Dépendances (mis à jour)

## Étapes de déploiement

### 1. Initialiser Git et pusher sur GitHub

```powershell
cd C:\Users\romai\Dropbox\Scripts\Aeronautics
git init
git add .
git commit -m "Initial commit - Meteo Bretagne VFR"
```

Créer le repository sur GitHub et pusher :
```powershell
git remote add origin https://github.com/OCDROM/meteo-bretagne-vfr.git
git branch -M main
git push -u origin main
```

### 2. Déployer sur Railway

1. Aller sur https://railway.app
2. Se connecter avec GitHub (OCDROM)
3. Cliquer "New Project"
4. Sélectionner "Deploy from GitHub repo"
5. Autoriser Railway à accéder à vos repos
6. Sélectionner le repo "meteo-bretagne-vfr"

### 3. Configurer les variables d'environnement

Dans Railway, onglet "Variables" :
- `METEO_USER` = `RMQR`
- `METEO_PASS` = `Njord562026`

### 4. Déployer !

Railway déploie automatiquement.
Votre URL sera : https://meteo-bretagne-vfr.up.railway.app (ou similaire)

---

Temps total : ~10 minutes
Coût : GRATUIT (500h/mois)
