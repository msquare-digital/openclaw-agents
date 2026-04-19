# ACInfinity Auth Setup (Milestone 1)

## Ziel
Read-only Zugriff fuer Klima- und Geraetewerte im GrowBox-Agent.

## Secret-Prinzip
- Keine Zugangsdaten in Git.
- Secrets nur auf dem Raspberry in `~/.openclaw-dev/secrets/` (dev) bzw. `~/.openclaw/secrets/` (prod).

## Empfohlene Secrets
- `ACINFINITY_EMAIL`
- `ACINFINITY_PASSWORD`
- Optional direktes App-Token: `ACINFINITY_TOKEN`
- Optional: `ACINFINITY_DEVICE_ID` (bei mehreren Controllern)
- Fuer lokalen Secret-Manager (`pass`):
  - `growbox/acinfinity/email`
  - `growbox/acinfinity/password`
  - optional `growbox/acinfinity/token`

## Ablauf (technisch)
1. Secrets lokal hinterlegen (`pass`, Datei oder Env).
2. Connector loggt sich via `appUserLogin` ein (Email/Passwort) und holt `appId` als Token.
3. Connector ruft `devInfoListAll` auf und extrahiert Temperatur/Feuchte/Luefterstufe.
4. Bei API-Fehlern klaren Status liefern statt leere Erfolgsantwort.

## Secret-Quellen (Reihenfolge)
### Token (optional, wenn Login uebersprungen werden soll)
1. `ACINFINITY_TOKEN`
2. `ACINFINITY_TOKEN_FILE`
3. `ACINFINITY_TOKEN_PASS_ENTRY` (Default: `growbox/acinfinity/token`)

### Email
1. `ACINFINITY_EMAIL`
2. `ACINFINITY_EMAIL_FILE`
3. `ACINFINITY_EMAIL_PASS_ENTRY` (Default: `growbox/acinfinity/email`)

### Passwort
1. `ACINFINITY_PASSWORD`
2. `ACINFINITY_PASSWORD_FILE`
3. `ACINFINITY_PASSWORD_PASS_ENTRY` (Default: `growbox/acinfinity/password`)

## Fehlercodes
- `auth_failed`: Login/Token ungueltig
- `api_unreachable`: Endpoint nicht erreichbar
- `rate_limited`: Anfragekontingent erreicht
- `schema_changed`: erwartete Felder fehlen

## Mindestoutput V1
- `air_temp_c`
- `humidity_pct`
- `airflow_pct` oder `fan_speed_pct`
