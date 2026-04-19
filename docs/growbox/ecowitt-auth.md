# Ecowitt Auth Setup (Milestone 1)

## Ziel
Read-only Zugriff auf Bodenfeuchte und Pumpenstatus.

## Secret-Prinzip
- Keine Zugangsdaten in Git.
- Secrets nur lokal auf dem Raspberry halten.

## Empfohlene Secrets
- `ECOWITT_APPLICATION_KEY`
- `ECOWITT_API_KEY`
- `ECOWITT_MAC` (Geraete-MAC)
- Fuer lokalen Secret-Manager (`pass`):
  - `growbox/ecowitt/application_key`
  - `growbox/ecowitt/api_key`
  - `growbox/ecowitt/mac`

## Ablauf (technisch)
1. Secrets lokal speichern (`chmod 600`).
2. Connector fragt `https://api.ecowitt.net/api/v3/device/real_time` per
   `application_key`, `api_key`, `mac` ab.
3. Polling liefert normalisierte Metriken gemaess Connector Contract.
4. Bei API-Fehlern klaren Status liefern statt leere Erfolgsantwort.

## Secret-Quellen (je Feld, Reihenfolge)
### Application Key
1. `ECOWITT_APPLICATION_KEY`
2. `ECOWITT_APPLICATION_KEY_FILE`
3. `ECOWITT_APPLICATION_KEY_PASS_ENTRY` (Default: `growbox/ecowitt/application_key`)

### API Key
1. `ECOWITT_API_KEY`
2. `ECOWITT_API_KEY_FILE`
3. `ECOWITT_API_KEY_PASS_ENTRY` (Default: `growbox/ecowitt/api_key`)

### MAC
1. `ECOWITT_MAC`
2. `ECOWITT_MAC_FILE`
3. `ECOWITT_MAC_PASS_ENTRY` (Default: `growbox/ecowitt/mac`)

## Fehlercodes
- `auth_failed`
- `api_unreachable`
- `rate_limited`
- `schema_changed`

## Mindestoutput V1
- `soil_moisture_pct`
- `pump_state`
