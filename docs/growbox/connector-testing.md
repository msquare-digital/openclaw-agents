# GrowBox Connector Testing

## Voraussetzungen
- Python 3 auf Entwicklungsmaschine oder Raspberry
- Fuer Live-Modus: API-Variablen/Secrets gesetzt

## Mock-Test (ohne externe APIs)
```bash
python3 workspaces/growbox/scripts/connectors/acinfinity_connector.py --mock
python3 workspaces/growbox/scripts/connectors/ecowitt_connector.py --mock
python3 workspaces/growbox/scripts/poll_growbox.py --mock
```

## Live-Test (Read-only)
Beispiel ACInfinity:
```bash
export ACINFINITY_API_BASE="https://<api-host>"
export ACINFINITY_DEVICE_ID="<device-id>"
export ACINFINITY_TOKEN_FILE="$HOME/.openclaw-dev/secrets/acinfinity-token"
python3 workspaces/growbox/scripts/connectors/acinfinity_connector.py
```

Beispiel Ecowitt:
```bash
export ECOWITT_API_BASE="https://<api-host>"
export ECOWITT_DEVICE_ID="<device-id>"
export ECOWITT_TOKEN_FILE="$HOME/.openclaw-dev/secrets/ecowitt-token"
python3 workspaces/growbox/scripts/connectors/ecowitt_connector.py
```

## Fehlerverhalten
- HTTP 401/403 -> `auth_failed`
- HTTP 429 -> `rate_limited`
- Netzwerk-/Timeout-Fehler -> `api_unreachable`
- Ungueltige Antwortstruktur -> `schema_changed`
