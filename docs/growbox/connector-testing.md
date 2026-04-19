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

## Live-Test mit Env-Datei (empfohlen)
```bash
cp workspaces/growbox/config/live.env.example workspaces/growbox/config/live.env
# live.env mit echten Werten fuellen (nicht committen)
bash workspaces/growbox/scripts/test_live_connectors.sh workspaces/growbox/config/live.env
```

Alternativ mit eigenem Pfad:
```bash
bash workspaces/growbox/scripts/test_live_connectors.sh /pfad/zu/live.env
```

## Live-Test mit pass (lokaler Secret-Manager auf Raspberry)
```bash
# auf Raspberry:
# 1) pass installieren und initialisieren (einmalig)
sudo apt update && sudo apt install -y pass gnupg2
gpg --full-generate-key
pass init "<DEIN_GPG_KEY_ID_ODER_EMAIL>"

# 2) Secrets speichern
pass insert growbox/acinfinity/email
pass insert growbox/acinfinity/password
# optional, falls schon vorhanden:
# pass insert growbox/acinfinity/token
pass insert growbox/ecowitt/application_key
pass insert growbox/ecowitt/api_key
pass insert growbox/ecowitt/mac

# 3) Env-Template fuer nicht geheime Werte kopieren
cp ~/.openclaw/workspace/growbox/config/live.pass.env.example ~/.openclaw/secrets/growbox.pass.env
chmod 600 ~/.openclaw/secrets/growbox.pass.env

# 4) Testlauf
bash ~/.openclaw/workspace/growbox/scripts/test_live_connectors.sh ~/.openclaw/secrets/growbox.pass.env
```

Hinweis: Connectoren unterstuetzen pro Secret drei Wege:
1. direkte Env-Variable
2. Secret-Datei (`*_FILE`)
3. pass-Eintrag (`*_PASS_ENTRY`)

## Live-Test (Read-only)
Beispiel ACInfinity:
```bash
export ACINFINITY_API_BASE="http://www.acinfinityserver.com"
export ACINFINITY_EMAIL_FILE="$HOME/.openclaw-dev/secrets/acinfinity-email"
export ACINFINITY_PASSWORD_FILE="$HOME/.openclaw-dev/secrets/acinfinity-password"
# optional:
# export ACINFINITY_DEVICE_ID="<acinfinity-device-id>"
python3 workspaces/growbox/scripts/connectors/acinfinity_connector.py
```

Beispiel Ecowitt:
```bash
export ECOWITT_API_BASE="https://api.ecowitt.net/api/v3"
export ECOWITT_APPLICATION_KEY_FILE="$HOME/.openclaw-dev/secrets/ecowitt-application-key"
export ECOWITT_API_KEY_FILE="$HOME/.openclaw-dev/secrets/ecowitt-api-key"
export ECOWITT_MAC_FILE="$HOME/.openclaw-dev/secrets/ecowitt-mac"
# Optional:
# export ECOWITT_SOIL_CHANNEL="1"
# export ECOWITT_PLUG_DEVICE_KEY="AC1100-00002A12"
python3 workspaces/growbox/scripts/connectors/ecowitt_connector.py
```

## Fehlerverhalten
- HTTP 401/403 -> `auth_failed`
- HTTP 429 -> `rate_limited`
- Netzwerk-/Timeout-Fehler -> `api_unreachable`
- Ungueltige Antwortstruktur -> `schema_changed`
