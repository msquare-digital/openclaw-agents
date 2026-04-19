# Ecowitt Auth Setup (Milestone 1)

## Ziel
Read-only Zugriff auf Bodenfeuchte und Pumpenstatus.

## Secret-Prinzip
- Keine Zugangsdaten in Git.
- Secrets nur lokal auf dem Raspberry halten.

## Empfohlene Secrets
- `ECOWITT_EMAIL`
- `ECOWITT_PASSWORD` oder API-Key
- Optional: `ECOWITT_DEVICE_ID`

## Ablauf (technisch)
1. Secrets lokal speichern (`chmod 600`).
2. Connector authentifiziert sich und cached Session-Infos kurzzeitig.
3. Polling liefert normalisierte Metriken gemaess Connector Contract.
4. Bei Auth-Fehlern klaren Status liefern statt leere Erfolgsantwort.

## Fehlercodes
- `auth_failed`
- `api_unreachable`
- `rate_limited`
- `schema_changed`

## Mindestoutput V1
- `soil_moisture_pct`
- `pump_state`
