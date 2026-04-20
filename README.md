# Phishing Awareness Backend (Flask)

This repository contains a lightweight Flask backend for a phishing-awareness demo.
Created: 2025-10-12 06:31:27Z

## What's included
- `server/app.py` : Flask backend implementing campaigns, targets, tracking and basic stats.
- `server/database.db` : (created on first run)
- `README.md` : this file.

## Prerequisites
- Python 3.8+
- backend knowledge for a better understanding
- (optional) virtualenv

## Setup & Run
```bash
cd phishing-platform
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install flask flask-cors
cd server
python app.py
```
Server will run at `http://127.0.0.1:5000`

## Default admin credentials
- username: `admin`
- password: `admin123`

## API Endpoints (summary)
- `POST /api/login` : JSON {username, password}
- `GET/POST /api/campaigns` : create or list campaigns
- `POST /api/campaigns/<id>/import_targets` : JSON {targets: ["a@b.com", ...]}
- `GET /api/campaigns/<id>/export` : CSV export of targets & tracking links
- `GET /track/<token>` : tracking route (records click)
- `GET /api/campaigns/<id>/stats` : campaign statistics

## Notes
- This project is for demo/local testing only. Do not use to send live phishing emails. and try to practice more
- For email sending in sandbox use MailHog or a sandboxed SMTP provider.
