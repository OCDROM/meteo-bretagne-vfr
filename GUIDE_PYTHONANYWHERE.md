# Guide de déploiement sur PythonAnywhere

## Étape 1 : Créer un compte PythonAnywhere (GRATUIT)

1. Aller sur https://www.pythonanywhere.com
2. Cliquer sur "Start running Python online in less than a minute"
3. Créer un compte gratuit (Beginner account)
   - Choisir un username (ex: romai ou rmqr)
   - Votre site sera : **username.pythonanywhere.com**

## Étape 2 : Uploader vos fichiers

### Option A : Via l'interface web (PLUS SIMPLE)

1. Une fois connecté, cliquer sur "Files" dans le menu
2. Créer un nouveau dossier : `meteo_bretagne`
3. Uploader les fichiers suivants :
   - `METAR.py`
   - `web_app.py`
   - `requirements.txt`
   - `credentials.txt`
   - `airports.csv` (si déjà téléchargé)
4. Créer le dossier `templates` dans `meteo_bretagne`
5. Uploader dans `templates/` :
   - `index.html`
   - `detail.html`
   - `error.html`

### Option B : Via Git (POUR EXPERTS)

1. Créer un repo GitHub avec vos fichiers
2. Dans PythonAnywhere, ouvrir un Bash console
3. Cloner votre repo : `git clone https://github.com/votre-username/votre-repo.git`

## Étape 3 : Installer les dépendances

1. Cliquer sur "Consoles" → "Bash"
2. Naviguer vers votre dossier :
   ```bash
   cd meteo_bretagne
   ```
3. Installer les dépendances :
   ```bash
   pip3.10 install --user Flask requests
   ```

## Étape 4 : Configurer les variables d'environnement (CREDENTIALS)

**IMPORTANT** : Ne pas uploader credentials.txt en clair !

1. Dans la Bash console :
   ```bash
   nano ~/.bashrc
   ```
2. Ajouter à la fin du fichier :
   ```bash
   export METEO_USER="votre_username"
   export METEO_PASS="votre_password"
   ```
3. Sauvegarder : CTRL+X, puis Y, puis Entrée
4. Recharger :
   ```bash
   source ~/.bashrc
   ```

## Étape 5 : Configurer l'application web

1. Aller sur l'onglet "Web"
2. Cliquer sur "Add a new web app"
3. Choisir "Manual configuration"
4. Choisir "Python 3.10"

### Configuration WSGI :

1. Cliquer sur le lien "WSGI configuration file"
2. **SUPPRIMER TOUT** le contenu existant
3. **REMPLACER** par :

```python
import sys
import os

# Ajouter votre projet au path
project_home = '/home/VOTRE_USERNAME/meteo_bretagne'
if project_home not in sys.path:
    sys.path = [project_home] + sys.path

# Importer votre application Flask
from web_app import app as application
```

**IMPORTANT** : Remplacer `VOTRE_USERNAME` par votre username PythonAnywhere

4. Cliquer sur "Save"

### Configuration du code source :

1. Retourner sur l'onglet "Web"
2. Dans "Code", section "Source code", mettre :
   ```
   /home/VOTRE_USERNAME/meteo_bretagne
   ```
3. Dans "Working directory", mettre :
   ```
   /home/VOTRE_USERNAME/meteo_bretagne
   ```

## Étape 6 : Lancer l'application

1. Retourner en haut de la page "Web"
2. Cliquer sur le gros bouton vert **"Reload VOTRE_USERNAME.pythonanywhere.com"**
3. Attendre quelques secondes
4. Cliquer sur le lien de votre site : **https://VOTRE_USERNAME.pythonanywhere.com**

## ✅ C'EST FINI !

Votre site est maintenant accessible publiquement :
- **https://VOTRE_USERNAME.pythonanywhere.com** - Tableau des aéroports
- **https://VOTRE_USERNAME.pythonanywhere.com/detail/LFRZ** - Détails d'un aéroport

## Partage avec d'autres personnes :

Donnez simplement l'URL à vos amis/famille/club d'aviation !

## Mise à jour des données :

Les données sont automatiquement rafraîchies toutes les 30 minutes.
Pour forcer une mise à jour : **https://VOTRE_USERNAME.pythonanywhere.com/api/refresh**

## Problèmes courants :

### "ImportError: No module named flask"
→ Installer Flask : `pip3.10 install --user Flask`

### "ImportError: No module named METAR"
→ Vérifier que METAR.py est bien dans le même dossier

### "Authentication failed"
→ Vérifier les variables d'environnement METEO_USER et METEO_PASS

### Erreur 500
→ Consulter les logs d'erreur dans l'onglet "Web" → "Error log"

## Support :

- Forum PythonAnywhere : https://www.pythonanywhere.com/forums/
- Documentation : https://help.pythonanywhere.com/

---

**Note de sécurité** : Le compte gratuit PythonAnywhere a des limitations de CPU.
Si votre site devient très populaire (>100,000 visites/jour), il faudra passer
au plan payant (5$/mois).
