# ACInfinity Auth Setup (Milestone 1)

## Ziel
Read-only Zugriff fuer Klima- und Geraetewerte im GrowBox-Agent.

## Secret-Prinzip
- Keine Zugangsdaten in Git.
- Secrets nur auf dem Raspberry in `~/.openclaw-dev/secrets/` (dev) bzw. `~/.openclaw/secrets/` (prod).

## Empfohlene Secrets
- `ACINFINITY_EMAIL`
- `ACINFINITY_PASSWORD` oder App-Token (falls verfuegbar)
- Optional: `ACINFINITY_DEVICE_ID` (bei mehreren Controllern)

## Ablauf (technisch)
1. Secret-Dateien auf dem Raspberry anlegen (`chmod 600`).
2. Connector liest Secrets aus Datei oder Env.
3. Beim Polling:
   - Session/Token holen oder refreshen
   - Daten abrufen
   - Bei 401/403 einmal Refresh versuchen
   - Danach `auth_failed` melden

## Fehlercodes
- `auth_failed`: Login/Token ungueltig
- `api_unreachable`: Endpoint nicht erreichbar
- `rate_limited`: Anfragekontingent erreicht
- `schema_changed`: erwartete Felder fehlen

## Mindestoutput V1
- `air_temp_c`
- `humidity_pct`
- `airflow_pct` oder `fan_speed_pct`
