# ASFIM Analytics Platform

Production-shaped Django/DRF platform for Moroccan OPCVM analytics, built around the existing `asfim.db` source.

## Local Run

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py import_asfim_sqlite --source asfim.db
python manage.py runserver 0.0.0.0:8000
```

Open `http://127.0.0.1:8000/`.

## Core API

- `GET /api/funds/`
- `GET /api/funds/{isin}/`
- `GET /api/funds/{isin}/history/`
- `GET /api/snapshot/`
- `GET /api/market-share/`
- `GET /api/market-overview/?start=&end=`: totals SQL côté serveur, variations, HHI, Top 3/5, répartitions par nature juridique/classification/souscripteurs, série d'actif net.
- `GET /api/sr-effect/`
- `GET /api/category-ranking/?classification=&metric=sr_effect|performance_effect|perf_1y&start=&end=&limit=`
- `GET /api/nav-series/?isins=ISIN1,ISIN2&start=&end=&base100=true`
- `GET /api/sr-effect-timeseries/?isins=&classification=&start=&end=`
- `GET /api/competitive/`
- `GET /api/data-quality/`

All analytics endpoints accept the common filters `classification`, `subscriber_type`, and `management_company` when applicable.

## Production Configuration

Set `APP_ENV` to a value other than `dev` in production. The following variables are then required or strongly recommended:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=0`
- `DJANGO_ALLOWED_HOSTS=example.com,www.example.com`
- `DATABASE_URL=postgres://...` plus `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`
- `DRF_ANON_THROTTLE_RATE` and `DRF_USER_THROTTLE_RATE` if the public API needs limits different from the defaults.

## Docker

```bash
docker compose up --build
```

After the containers are up, import the legacy data into Postgres:

```bash
docker compose exec web python manage.py import_asfim_sqlite --source asfim.db
```

## Reports

```bash
python manage.py export_report --output reports/asfim_report.pdf
```
