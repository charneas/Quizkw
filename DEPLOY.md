# Guide de Déploiement - Quizkw (Linux + Gunicorn + Nginx)

Ce guide explique comment déployer Quizkw en production sur un serveur Linux avec Gunicorn (backend) et Nginx (reverse proxy + frontend statique).

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
cd /opt
sudo git clone https://github.com/charneas/Quizkw.git
sudo chown -R $USER:$USER /opt/Quizkw
cd /opt/Quizkw
```

## 3. Configuration du Backend

### 3.1 Environnement virtuel Python

```bash
cd /opt/Quizkw/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

### 3.2 Variables d'environnement

```bash
# Créer un fichier .env pour la production
cat > /opt/Quizkw/backend/.env << EOF
DATABASE_URL=sqlite:///./quizkw.db
# Pour PostgreSQL (recommandé en production) :
# DATABASE_URL=postgresql://quizkw_user:mot_de_passe_securise@localhost/quizkw_db
EOF
```

### 3.3 Initialiser la base de données

```bash
cd /opt/Quizkw/backend
source venv/bin/activate
python seed.py
```

### 3.4 Tester Gunicorn

```bash
cd /opt/Quizkw/backend
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
User=$USER
Group=$USER
WorkingDirectory=/opt/Quizkw/backend
Environment="PATH=/opt/Quizkw/backend/venv/bin"
EnvironmentFile=/opt/Quizkw/backend/.env
ExecStart=/opt/Quizkw/backend/venv/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 127.0.0.1:8000
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

## 5. Build du Frontend

```bash
cd /opt/Quizkw/frontend
npm install
npm run build
```

Le build sera dans `frontend/dist/`. C'est ce dossier que Nginx servira.

## 6. Configuration Nginx

```bash
sudo tee /etc/nginx/sites-available/quizkw << EOF
server {
    listen 80;
    server_name votre-domaine.com;  # Remplacer par votre domaine ou IP

    # Frontend - fichiers statiques
    root /opt/Quizkw/frontend/dist;
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
sudo ln -sf /etc/nginx/sites-available/quizkw /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Tester la configuration
sudo nginx -t

# Relancer Nginx
sudo systemctl restart nginx
```

## 7. HTTPS avec Let's Encrypt (optionnel mais recommandé)

```bash
# Installer Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtenir un certificat SSL
sudo certbot --nginx -d votre-domaine.com

# Le renouvellement automatique est configuré via un timer systemd
sudo systemctl status certbot.timer
```

## 8. PostgreSQL (recommandé pour la production)

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
cd /opt/Quizkw/backend
source venv/bin/activate
pip install psycopg2-binary

# Mettre à jour le .env
# DATABASE_URL=postgresql://quizkw_user:mot_de_passe_securise@localhost/quizkw_db
```

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
sudo systemctl restart quizkw-backend

# Reconstruire le frontend après modification
cd /opt/Quizkw/frontend && npm run build

# Mettre à jour depuis GitHub
cd /opt/Quizkw
git pull
cd backend && source venv/bin/activate && pip install -r requirements.txt
cd ../frontend && npm install && npm run build
sudo systemctl restart quizkw-backend
```

## 11. Script de déploiement rapide

Créer un script `/opt/Quizkw/deploy.sh` :

```bash
#!/bin/bash
set -e

echo "📦 Mise à jour du code..."
cd /opt/Quizkw
git pull

echo "🐍 Mise à jour du backend..."
cd backend
source venv/bin/activate
pip install -r requirements.txt

echo "⚛️  Build du frontend..."
cd ../frontend
npm install
npm run build

echo "🔄 Redémarrage des services..."
sudo systemctl restart quizkw-backend
sudo systemctl reload nginx

echo "✅ Déploiement terminé !"
echo "Santé API: $(curl -s http://localhost:8000/health)"
```

```bash
chmod +x /opt/Quizkw/deploy.sh
```

## Architecture déployée

```
Client (navigateur)
    │
    ▼
┌──────────────────┐
│   Nginx (:80)    │
│                  │
│  /       → dist/ │  ← Frontend React (fichiers statiques)
│  /api/   → :8000 │  ← Proxy vers Gunicorn
└──────────────────┘
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
| Frontend blank | Vérifier le build : `ls /opt/Quizkw/frontend/dist/` |
| API CORS errors | Vérifier que les requêtes passent par `/api/` et non directement |
| Permission denied | `sudo chown -R $USER:$USER /opt/Quizkw` |
| Port 8000 in use | `sudo lsof -i :8000` puis kill le process |
