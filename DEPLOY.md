# Guide de Déploiement - Quizkw (Linux + Gunicorn + Nginx)

Ce guide explique comment déployer Quizkw en production sur un serveur Linux avec Gunicorn (backend) et Nginx (reverse proxy + frontend statique).

> **Convention de ce guide** : `<SERVEUR>` = IP ou domaine du serveur, `<UTILISATEUR>` = utilisateur de déploiement, `<CHEMIN_APP>` = répertoire où le dépôt est cloné (ex. `/home/<UTILISATEUR>/Quizkw`, pas nécessairement `/opt/Quizkw`). Remplacer par les valeurs réelles de l'environnement — volontairement non documentées ici car ce dépôt est public.

## Prérequis

- Serveur Linux (Ubuntu 22.04+ recommandé)
- Python 3.10+
- Node.js 18+ (pour le build du frontend)
- Nginx
- Git

## 1. Préparation du serveur

```bash
# Mise à jour du système
sudo apt update && sudo apt upgrade -y

# Installation des dépendances système
sudo apt install -y python3 python3-pip python3-venv nginx git curl

# Installation de Node.js 20 (pour build frontend)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

## 2. Cloner le projet

```bash
cd <CHEMIN_APP_PARENT>
git clone https://github.com/charneas/Quizkw.git
cd <CHEMIN_APP>
```

Cloner directement en tant qu'utilisateur de déploiement (pas de `sudo git clone` + `chown` nécessaire si l'utilisateur possède déjà le répertoire parent) — évite un aller-retour de permissions inutile.

## 3. Configuration du Backend

### 3.1 Environnement virtuel Python

```bash
cd <CHEMIN_APP>/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Piège connu (Python 3.13+, ex. Python 3.14)** : `psycopg2-binary` n'a pas toujours de wheel précompilé disponible pour les versions très récentes de Python, et sa compilation depuis les sources échoue (`_PyInterpreterState_Get` introuvable). Comme la production tourne sur **SQLite** par défaut (`DATABASE_URL=sqlite:///./quizkw.db`), `psycopg2-binary` n'est **pas requis** tant que PostgreSQL n'est pas activé (section 8) — un échec de build de ce seul paquet n'est pas bloquant. Vérifier que le reste s'est installé : `python -c "import fastapi, alembic, sqlalchemy; print('ok')"`.

### 3.2 Variables d'environnement

```bash
# Créer un fichier .env pour la production
cat > <CHEMIN_APP>/backend/.env << EOF
DATABASE_URL=sqlite:///./quizkw.db
# Pour PostgreSQL (recommandé en production) :
# DATABASE_URL=postgresql://quizkw_user:mot_de_passe_securise@localhost/quizkw_db

# Requis depuis l'Epic F-ext-2 (AD-17, authentification admin) : secret de
# signature du cookie de session /admin/*. Générer une valeur aléatoire unique
# par déploiement (ex. openssl rand -hex 32) — jamais la valeur d'exemple ci-dessous.
SESSION_SECRET_KEY=<valeur-aleatoire-generee-par-deploiement>
# SESSION_COOKIE_SECURE=true est le défaut (cookie envoyé uniquement en HTTPS,
# cohérent avec la section 7 ci-dessous) ; ne le mettre à false qu'en dev local HTTP.

# Requis depuis l'Epic F (génération semi-automatique de contenu admin) : clé
# API Anthropic utilisée par l'endpoint de génération de questions. Sans cette
# variable, le reste du site fonctionne normalement — seule la génération de
# contenu admin échoue.
ANTHROPIC_API_KEY=<cle-api-anthropic>
EOF
```

### 3.3 Initialiser la base de données

```bash
cd <CHEMIN_APP>/backend
source venv/bin/activate
python seed.py
```

### 3.4 Tester Gunicorn

```bash
cd <CHEMIN_APP>/backend
source venv/bin/activate
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000
```

Vérifier que ça fonctionne : `curl http://localhost:8000/health`

## 4. Service Systemd pour le Backend

Créer un service pour que Gunicorn démarre automatiquement :

```bash
sudo tee /etc/systemd/system/quizkw-backend.service << EOF
[Unit]
Description=Quizkw Backend API (Gunicorn)
After=network.target

[Service]
User=<UTILISATEUR>
Group=<UTILISATEUR>
WorkingDirectory=<CHEMIN_APP>/backend
Environment="PATH=<CHEMIN_APP>/backend/venv/bin"
EnvironmentFile=<CHEMIN_APP>/backend/.env
ExecStart=<CHEMIN_APP>/backend/venv/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 127.0.0.1:8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
```

```bash
# Activer et démarrer le service
sudo systemctl daemon-reload
sudo systemctl enable quizkw-backend
sudo systemctl start quizkw-backend

# Vérifier le statut
sudo systemctl status quizkw-backend
```

### 4.1 Sudoers restreint pour l'utilisateur de déploiement (recommandé)

Plutôt que de donner un accès `sudo` complet à l'utilisateur de déploiement, limiter aux seules commandes nécessaires via `visudo` (`/etc/sudoers.d/quizkw-deploy`) :

```
<UTILISATEUR> ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart quizkw-backend, \
  /usr/bin/systemctl status quizkw-backend, \
  /usr/bin/systemctl daemon-reload, \
  /usr/bin/systemctl enable quizkw-backend, \
  /usr/bin/systemctl start quizkw-backend, \
  /usr/bin/systemctl reload nginx, \
  /usr/bin/systemctl restart nginx, \
  /usr/bin/apt-get update, /usr/bin/apt-get install *, \
  /usr/sbin/nginx -t, \
  /usr/bin/tee /etc/systemd/system/quizkw-backend.service, \
  /usr/bin/tee /etc/nginx/sites-available/quizkw, \
  /usr/bin/ln -sf /etc/nginx/sites-available/quizkw /etc/nginx/sites-enabled/quizkw
```

**Important** : ces règles matchent la commande **exacte** (chemin absolu, sans arguments additionnels au-delà de ceux listés). `sudo systemctl status quizkw-backend --no-pager -l` échouera même si `sudo /usr/bin/systemctl status quizkw-backend` fonctionne — appeler les binaires par leur chemin absolu (`/usr/bin/systemctl`, `/usr/sbin/nginx`) sans flags supplémentaires quand on script un déploiement avec cet utilisateur.

## 5. Build du Frontend

```bash
cd <CHEMIN_APP>/frontend
npm ci
npm run build
```

Le build sera dans `frontend/dist/`. C'est ce dossier que Nginx servira. Préférer `npm ci` à `npm install` en déploiement : il installe exactement les versions de `package-lock.json` sans le régénérer (évite un diff parasite sur ce fichier au prochain `git pull`).

## 6. Configuration Nginx

```bash
sudo tee /etc/nginx/sites-available/quizkw << EOF
# Bloc HTTP (:80) — uniquement redirection vers HTTPS + validation ACME Certbot.
# Ne PAS rediriger /.well-known/acme-challenge/ : c'est le chemin que Certbot
# utilise pour valider le domaine (HTTP-01). Une redirection totale du port 80
# casse cette validation en boucle.
server {
    listen 80;
    server_name <SERVEUR>;  # IP ou domaine — match exact du Host demandé

    location /.well-known/acme-challenge/ {
        root <CHEMIN_APP>/frontend/dist;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

# Bloc HTTPS (:443) — contenu applicatif complet + certificats Let's Encrypt.
# Les chemins ssl_certificate*/n'existent pas tant que la commande Certbot de
# la section 7 n'a pas tourné une première fois : voir la note juste après ce
# bloc avant d'activer le site sur un serveur neuf.
server {
    listen 443 ssl;
    server_name <SERVEUR>;  # IP ou domaine — doit matcher le -d passé à certbot (section 7)

    ssl_certificate     /etc/letsencrypt/live/<SERVEUR>/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/<SERVEUR>/privkey.pem;

    # max-age volontairement court (1h) tant que le certificat n'a pas été
    # vérifié en conditions réelles (cf. H-006) : un HSTS à 1 an poserait un
    # verrou navigateur d'un an si le certificat échoue après mise en prod.
    # Augmenter progressivement une fois le premier déploiement HTTPS validé.
    add_header Strict-Transport-Security "max-age=3600" always;

    # Frontend - fichiers statiques
    root <CHEMIN_APP>/frontend/dist;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 256;

    # Frontend SPA - toutes les routes non-API renvoient vers index.html
    location / {
        try_files \$uri \$uri/ /index.html;
    }

    # API Backend - proxy vers Gunicorn
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket support (pour futur temps réel)
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Cache pour les assets statiques
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
EOF
```

```bash
# Activer le site
sudo ln -sf /etc/nginx/sites-available/quizkw /etc/nginx/sites-enabled/quizkw

# Tester la configuration
sudo nginx -t

# Relancer Nginx
sudo systemctl restart nginx
```

**Ordre important, serveur neuf** : `nginx -t` échouera tant que Certbot (section 7) n'a pas obtenu un premier certificat aux chemins `/etc/letsencrypt/live/<SERVEUR>/` — `listen 443 ssl;` sans `ssl_certificate`/`ssl_certificate_key` valides fait échouer le test même si seules ces deux lignes sont commentées. Sur un serveur neuf, commenter **tout le bloc `server { listen 443 ssl; ... }`** (pas seulement les deux lignes de certificat) le temps du premier `nginx -t` / `systemctl restart nginx` de cette section, puis le réactiver après avoir exécuté la commande Certbot de la section 7. Vérifier après coup (`sudo nginx -t` puis `cat /etc/nginx/sites-available/quizkw`) que Certbot a bien laissé les chemins de certificat intacts dans le bloc réactivé, avant de considérer cette étape terminée.

**`<SERVEUR>` doit être un nom de domaine, pas une IP nue, avant cette étape** : Certbot ne délivre pas de certificat pour une IP (section 7). Si `<SERVEUR>` est encore une IP au moment d'activer le bloc 443, remplacer `<SERVEUR>` par le domaine réel dans les deux blocs (80 et 443) avant de continuer — sinon `server_name`/`ssl_certificate` pointent vers un domaine qui ne correspond à rien.

**Note sur le site `default` de Nginx** : il n'est pas nécessaire de le supprimer (`rm /etc/nginx/sites-enabled/default`) si `server_name` du site `quizkw` matche exactement `<SERVEUR>` — Nginx route par `Host` header, donc une requête avec le bon `Host` atteint bien `quizkw`, et `default` sert simplement de filet pour tout autre nom (y compris `localhost` en test via SSH local, ce qui peut surprendre en diagnostic : tester depuis l'extérieur avec la vraie adresse plutôt que `curl localhost` sur le serveur pour éviter un faux négatif).

## 7. HTTPS avec Let's Encrypt (obligatoire — actuellement absent en prod, cf. H-006)

Le bloc Nginx de la section 6 (port 80 en redirection + port 443 avec chemins de certificats) doit déjà être actif (site activé, `nginx -t` passé) avant d'exécuter Certbot : le plugin `--nginx` a besoin d'un site déjà en place pour y injecter/rafraîchir le certificat.

```bash
# Installer Certbot
sudo apt install -y certbot python3-certbot-nginx

# Ouvrir le firewall pour HTTPS avant d'aller plus loin (section 9) — sinon la
# validation ACME et l'accès HTTPS final restent bloqués après cette étape
sudo ufw allow 443/tcp

# Obtenir un certificat SSL (nécessite un nom de domaine, pas une IP nue) et
# l'injecter dans le bloc 443 de la section 6 (server_name doit correspondre à -d)
sudo certbot --nginx -d votre-domaine.com

# Le renouvellement automatique est configuré via un timer systemd
sudo systemctl status certbot.timer

# Vérifier que le certificat est bien servi (depuis une machine externe, pas
# le serveur lui-même — voir la remarque sur curl localhost section 6)
curl -I https://votre-domaine.com
```

**Statut actuel (mis à jour 2026-07-29, Epic F-ext-2)** : HTTPS est réellement actif en production — la note précédente indiquant l'absence de domaine/certificat vérifié était périmée. `SESSION_COOKIE_SECURE` (Epic F-ext-2, cookie de session admin) est donc activé par défaut sans risque de casser le login admin sur cette prod.

## 8. PostgreSQL (optionnel, pas encore utilisé en prod)

```bash
# Installation
sudo apt install -y postgresql postgresql-contrib

# Créer la base de données
sudo -u postgres psql << EOF
CREATE USER quizkw_user WITH PASSWORD 'mot_de_passe_securise';
CREATE DATABASE quizkw_db OWNER quizkw_user;
GRANT ALL PRIVILEGES ON DATABASE quizkw_db TO quizkw_user;
EOF

# Installer le driver Python
cd <CHEMIN_APP>/backend
source venv/bin/activate
pip install psycopg2-binary

# Mettre à jour le .env
# DATABASE_URL=postgresql://quizkw_user:mot_de_passe_securise@localhost/quizkw_db
```

Si `pip install psycopg2-binary` échoue à la compilation (Python très récent sans wheel précompilé, cf. section 3.1), utiliser `psycopg[binary]` (le paquet successeur, activement maintenu) ou installer un Python legacy dédié au venv backend plutôt que le Python système le plus récent.

## 9. Firewall

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

## 10. Commandes utiles

```bash
# Voir les logs du backend
sudo journalctl -u quizkw-backend -f

# Redémarrer le backend après modification
sudo /usr/bin/systemctl restart quizkw-backend

# Reconstruire le frontend après modification
cd <CHEMIN_APP>/frontend && npm run build

# Mettre à jour depuis GitHub
cd <CHEMIN_APP>
git status                      # vérifier l'absence de modifications locales avant de pull
git pull
cd backend && source venv/bin/activate && pip install -r requirements.txt  # seulement si requirements.txt a changé
cd ../frontend && npm ci && npm run build
sudo /usr/bin/systemctl restart quizkw-backend
```

## 11. Script de déploiement rapide

Créer un script `<CHEMIN_APP>/deploy.sh` :

```bash
#!/bin/bash
set -e

echo "📦 Mise à jour du code..."
cd <CHEMIN_APP>
git status --short   # à vérifier manuellement : ce script ne pull pas si des fichiers locaux sont modifiés
git pull

echo "🐍 Mise à jour du backend..."
cd backend
source venv/bin/activate
# N'exécuter que si requirements.txt a changé dans le diff — un pip install
# systématique peut échouer sur des paquets non critiques (ex. psycopg2-binary
# sur un Python très récent) alors que rien n'en a besoin en pratique.
pip install -r requirements.txt || echo "⚠️  pip install a échoué — vérifier si un paquet non critique (ex. psycopg2-binary) est en cause avant de bloquer le déploiement"

echo "⚛️  Build du frontend..."
cd ../frontend
npm ci
npm run build

echo "🔄 Redémarrage des services..."
sudo /usr/bin/systemctl restart quizkw-backend
sudo /usr/bin/systemctl reload nginx

echo "✅ Déploiement terminé !"
echo "Santé API: $(curl -s http://localhost:8000/health)"
```

```bash
chmod +x <CHEMIN_APP>/deploy.sh
```

## Architecture déployée

```
Client (navigateur)
    │
    ▼
┌──────────────────────────┐
│ Nginx (:80 → 301 → :443) │
│ Nginx (:443, TLS)        │
│                          │
│  /       → dist/         │  ← Frontend React (fichiers statiques)
│  /api/   → :8000         │  ← Proxy vers Gunicorn
└──────────────────────────┘
         │
         ▼
┌──────────────────┐
│ Gunicorn (:8000) │
│  4 workers       │
│  UvicornWorker   │
│  → FastAPI       │
└──────────────────┘
         │
         ▼
┌──────────────────┐
│  SQLite / PgSQL  │
└──────────────────┘
```

## Dépannage

| Problème | Solution |
|----------|----------|
| 502 Bad Gateway | Vérifier que Gunicorn tourne : `systemctl status quizkw-backend` |
| Frontend blank | Vérifier le build : `ls <CHEMIN_APP>/frontend/dist/` |
| API CORS errors | Vérifier que les requêtes passent par `/api/` et non directement |
| Permission denied | Vérifier que l'utilisateur de déploiement possède `<CHEMIN_APP>` (`ls -la`), pas de `chown` récursif nécessaire si le clone a été fait par cet utilisateur dès le départ |
| Port 8000 in use | `sudo lsof -i :8000` puis kill le process |
| `curl localhost/` sert la page par défaut Nginx | Normal si `server_name` du site ne matche pas la chaîne `localhost` — tester avec la vraie adresse publique, ou `curl -H "Host: <SERVEUR>" localhost/` |
| `pip install -r requirements.txt` échoue sur `psycopg2-binary` | Non bloquant si la prod tourne sur SQLite (`DATABASE_URL=sqlite:...`) ; voir section 3.1 |
| `sudo <commande>` refusée alors qu'elle est dans la liste `sudo -l` | La commande doit matcher exactement l'entrée sudoers (chemin absolu, mêmes arguments, sans flag additionnel) |
