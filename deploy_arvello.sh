#!/bin/bash

# Boje za bolju čitljivost
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # Bez boje

# ASCII art za Arvello
echo -e "${BLUE}"
echo "    _                     _ _       "
echo "   / \\   _ ____   _____| | | ___  "
echo "  / _ \\ | '__\\ \\ / / _ \\ | |/ _ \\ "
echo " / ___ \\| |   \\ V /  __/ | | (_) |"
echo "/_/   \\_\\_|    \\_/ \\___|_|_|\\___/ "
echo -e "${NC}"
echo "Arvello - Skripta za produkcijsko postavljanje"
echo "=============================================="

# Provjera root privilegija
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Ova skripta mora biti pokrenuta kao root korisnik${NC}" 
   exit 1
fi

# Provjera ovisnosti
echo -e "\n${YELLOW}Provjeravam potrebne pakete...${NC}"
for cmd in curl git; do
    if ! command -v $cmd &> /dev/null; then
        echo -e "${RED}$cmd nije instaliran. Instaliram...${NC}"
        apt-get update && apt-get install -y $cmd || { echo -e "${RED}Neuspjela instalacija $cmd${NC}"; exit 1; }
    fi
done

# Korisnički unos podataka
echo -e "\n${YELLOW}Molimo unesite sljedeće podatke za Arvello instalaciju:${NC}"
read -p "Naziv domene (FQDN, npr. arvello.example.com): " DOMAIN_NAME
read -p "Naziv PostgreSQL baze [arvello]: " DB_NAME
DB_NAME=${DB_NAME:-arvello}
read -p "PostgreSQL korisničko ime [arvello_user]: " DB_USER
DB_USER=${DB_USER:-arvello_user}
read -sp "PostgreSQL lozinka: " DB_PASSWORD
echo
read -p "Django admin korisničko ime [admin]: " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-admin}
read -sp "Django admin lozinka: " ADMIN_PASSWORD
echo
read -p "Email poslužitelj (npr. smtp.gmail.com): " EMAIL_HOST
read -p "Email port [587]: " EMAIL_PORT
EMAIL_PORT=${EMAIL_PORT:-587}
read -p "Email korisničko ime: " EMAIL_USER
read -sp "Email lozinka: " EMAIL_PASSWORD
echo
read -p "HTTP port za Arvello [8000]: " HTTP_PORT
HTTP_PORT=${HTTP_PORT:-8000}

# Generiranje Django tajnog ključa
echo -e "\n${YELLOW}Generiram sigurnosni ključ...${NC}"
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')

# Ažuriranje sustava
echo -e "\n${YELLOW}Ažuriram sistemske pakete...${NC}"
apt-get update && apt-get upgrade -y

# Instalacija potrebnih paketa
echo -e "\n${YELLOW}Instaliram potrebne pakete...${NC}"
apt-get install -y python3 python3-venv python3-pip postgresql postgresql-contrib git nginx

# Instaliraj ovisnosti za WeasyPrint
echo -e "\n${YELLOW}Instaliram ovisnosti za WeasyPrint...${NC}"
apt-get install -y libglib2.0-0 libpango-1.0-0 libpangocairo-1.0-0 libcairo2 \
    libharfbuzz0b libffi-dev libpangoft2-1.0-0 libcairo-gobject2 \
    libgdk-pixbuf-2.0-0 shared-mime-info \
    build-essential libcairo2-dev libpango1.0-dev || {
    echo -e "${RED}Neuspjela instalacija WeasyPrint ovisnosti. PDF funkcionalnost možda neće raditi ispravno.${NC}"
}

# Postavljanje PostgreSQL-a
echo -e "\n${YELLOW}Postavljam PostgreSQL...${NC}"
if su postgres -c "psql -c \"CREATE DATABASE $DB_NAME;\"" 2>/dev/null &&
   su postgres -c "psql -c \"CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';\"" 2>/dev/null &&
   su postgres -c "psql -c \"ALTER ROLE $DB_USER SET client_encoding TO 'utf8';\"" 2>/dev/null &&
   su postgres -c "psql -c \"ALTER ROLE $DB_USER SET default_transaction_isolation TO 'read committed';\"" 2>/dev/null &&
   su postgres -c "psql -c \"ALTER ROLE $DB_USER SET timezone TO 'Europe/Zagreb';\"" 2>/dev/null &&
   su postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;\"" 2>/dev/null
then
   echo -e "${GREEN}PostgreSQL uspješno postavljen.${NC}"
else
   echo -e "${RED}Neuspjelo postavljanje PostgreSQL-a. Molimo provjerite gornje poruke o greškama.${NC}"
   exit 1
fi

# Kloniranje repozitorija
echo -e "\n${YELLOW}Kloniram Arvello repozitorij...${NC}"
mkdir -p /opt/arvello
if git clone https://github.com/fmis13/arvello.git /opt/arvello/arvello; then
   echo -e "${GREEN}Arvello repozitorij uspješno kloniran.${NC}"
else
   echo -e "${RED}Neuspjelo kloniranje Arvello repozitorija. Molimo provjerite gornje poruke o greškama.${NC}"
   exit 1
fi

# Postavljanje virtualnog okruženja
echo -e "\n${YELLOW}Postavljam Python virtualno okruženje...${NC}"
python3 -m venv /opt/arvello/venv
source /opt/arvello/venv/bin/activate
pip install --upgrade pip

# Instaliraj stabilnu verziju Pillow-a i izbjegni yanked verziju
echo -e "\n${YELLOW}Instaliram stabilnu verziju Pillow-a...${NC}"
pip install pillow==10.2.0

if pip install -r /opt/arvello/arvello/requirements.txt && 
   pip install gunicorn psycopg2-binary python-decouple; then
   echo -e "${GREEN}Python virtualno okruženje uspješno postavljeno.${NC}"
else
   echo -e "${RED}Neuspjelo postavljanje Python virtualnog okruženja. Molimo provjerite gornje poruke o greškama.${NC}"
   exit 1
fi

# Stvaranje .env datoteke
echo -e "\n${YELLOW}Kreiram .env datoteku...${NC}"
cat > /opt/arvello/arvello/arvello/.env << EOF
# Django postavke
DJANGO_SECRET_KEY=$SECRET_KEY
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=$DOMAIN_NAME,localhost,127.0.0.1

# Postavke baze podataka
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_HOST=localhost
DB_PORT=5432

# Email postavke
EMAIL_HOST=$EMAIL_HOST
EMAIL_PORT=$EMAIL_PORT
EMAIL_HOST_USER=$EMAIL_USER
EMAIL_HOST_PASSWORD=$EMAIL_PASSWORD
EMAIL_USE_TLS=True
EOF
echo -e "${GREEN}.env datoteka uspješno kreirana.${NC}"

# Stvaranje local_settings.py datoteke
echo -e "\n${YELLOW}Kreiram local_settings.py...${NC}"
cat > /opt/arvello/arvello/arvello/local_settings.py << 'EOF'
from decouple import config
import os

# Postavke baze podataka
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432', cast=int),
    }
}

# Sigurnosne postavke
DEBUG = config('DJANGO_DEBUG', default=False, cast=bool)
SECRET_KEY = config('DJANGO_SECRET_KEY')
ALLOWED_HOSTS = config('DJANGO_ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

# Email postavke
EMAIL_HOST = config('EMAIL_HOST')
EMAIL_PORT = config('EMAIL_PORT', cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)

# Statičke datoteke
STATIC_URL = '/static/'
MEDIA_URL = '/media/'
STATIC_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'staticfiles')
MEDIA_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'media')
EOF
echo -e "${GREEN}local_settings.py uspješno kreirana.${NC}"

# Ažuriranje settings.py datoteke
echo -e "\n${YELLOW}Ažuriram settings.py za učitavanje lokalnih postavki...${NC}"
grep -q "from .local_settings import" /opt/arvello/arvello/arvello/settings.py
if [ $? -ne 0 ]; then
    cat >> /opt/arvello/arvello/arvello/settings.py << 'EOF'

# Učitaj lokalne postavke - produkcijske postavke
try:
    from .local_settings import *
except ImportError:
    pass
EOF
    echo -e "${GREEN}settings.py uspješno ažuriran.${NC}"
else
    echo -e "${GREEN}settings.py već uključuje local_settings.${NC}"
fi

# Postavljanje Djanga
echo -e "\n${YELLOW}Postavljam Django...${NC}"
cd /opt/arvello/arvello/arvello
if python manage.py makemigrations; then
   echo -e "${GREEN}Priprema migracije baze podataka uspješno završena.${NC}"
else
   echo -e "${RED}Neuspjela priprema migracije baze podataka. Molimo provjerite gornje poruke o greškama.${NC}"
   exit 1
fi
if python manage.py migrate; then
   echo -e "${GREEN}Migracija baze podataka uspješno završena.${NC}"
else
   echo -e "${RED}Neuspjela migracija baze podataka. Molimo provjerite gornje poruke o greškama.${NC}"
   exit 1
fi

if echo "from django.contrib.auth.models import User; User.objects.filter(username='$ADMIN_USER').exists() or User.objects.create_superuser('$ADMIN_USER', '$EMAIL_USER', '$ADMIN_PASSWORD')" | python manage.py shell; then
   echo -e "${GREEN}Admin korisnik uspješno kreiran.${NC}"
else
   echo -e "${RED}Neuspjelo kreiranje admin korisnika. Molimo provjerite gornje poruke o greškama.${NC}"
   exit 1
fi

if python manage.py collectstatic --noinput; then
   echo -e "${GREEN}Statičke datoteke uspješno prikupljene.${NC}"
else
   echo -e "${RED}Neuspjelo prikupljanje statičkih datoteka. Molimo provjerite gornje poruke o greškama.${NC}"
   exit 1
fi

# Postavljanje Nginx konfiguracije
echo -e "\n${YELLOW}Postavljam Nginx konfiguraciju...${NC}"
# Ensure DOMAIN_NAME has a default value if empty
if [ -z "$DOMAIN_NAME" ]; then
    DOMAIN_NAME="_"  # Nginx default server that matches any hostname
    echo -e "${YELLOW}Upozorenje: Naziv domene nije postavljen. Koristim '_' kao zamjensku vrijednost.${NC}"
fi

# Dohvati IP adresu servera
SERVER_IP=$(hostname -I | awk '{print $1}')

cat > /etc/nginx/sites-available/arvello << EOF
server {
    listen 80 default_server;
    server_name ${DOMAIN_NAME} ${SERVER_IP} localhost;

    # Dodane lokacije za statičke datoteke
    location /static/ {
        alias /opt/arvello/arvello/arvello/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000";
    }

    location /media/ {
        alias /opt/arvello/arvello/arvello/media/;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000";
    }

    location / {
        proxy_pass http://127.0.0.1:$HTTP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Aktiviranje Nginx konfiguracije i onemogućavanje zadane konfiguracije
ln -sf /etc/nginx/sites-available/arvello /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Provjera sintakse Nginx konfiguracije
nginx -t && systemctl restart nginx || echo -e "${RED}Greška u Nginx konfiguraciji${NC}"

# Postavljanje Systemd servisa za Gunicorn
echo -e "\n${YELLOW}Postavljam Systemd servis za Gunicorn...${NC}"
cat > /etc/systemd/system/arvello.service << EOF
[Unit]
Description=Arvello Gunicorn daemon
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/arvello/arvello/arvello
ExecStart=/opt/arvello/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:$HTTP_PORT arvello.wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# Postavljanje odgovarajućih dozvola
echo -e "\n${YELLOW}Postavljam odgovarajuće dozvole za datoteke...${NC}"
chown -R www-data:www-data /opt/arvello
chmod -R 750 /opt/arvello

# Pokretanje i omogućavanje servisa
systemctl daemon-reload
systemctl enable arvello
systemctl start arvello

echo -e "\n${GREEN}Arvello instalacija je završena!${NC}"
echo -e "\n${YELLOW}Informacije o sustavu:${NC}"
echo -e "  • Arvello je dostupan preko:"
echo -e "    - http://${DOMAIN_NAME}"
echo -e "    - http://${SERVER_IP}"
echo -e "  • Direktan pristup Gunicorn-u: http://localhost:$HTTP_PORT (samo s lokalnog računala)"
echo -e "  • VAŽNO: Za pristup s drugih računala koristite gore navedene URL-ove"

echo -e "\n${YELLOW}Admin vjerodajnice:${NC}"
echo -e "  • Korisničko ime: $ADMIN_USER"
echo -e "  • Lozinka: [Unesena tijekom instalacije]"

echo -e "\n${YELLOW}Sljedeći koraci:${NC}"
echo -e "  1. Postavite Nginx Proxy Manager za prosljeđivanje zahtjeva na http://IP_VAŠEG SERVERA:$HTTP_PORT"
echo -e "  2. Konfigurirajte SSL s Let's Encrypt kroz Nginx Proxy Manager"
echo -e "  3. Pristupi Arvellu na http://$DOMAIN_NAME"

echo -e "\n${BLUE}Hvala što ste instalirali Arvello!${NC}"
