# openclaw-dev

Git-repo fuer versionierbare OpenClaw-Agenten und Workspaces.

## Struktur
- `agents/<id>/agent/`: agent-spezifische OpenClaw-Agent-Configs (ohne Laufzeit-/Auth-State)
- `workspaces/main`: Dateien fuer den `main` Agent
- `workspaces/mail`: Dateien fuer den `mail` Agent
- `workspaces/pricewatch`: Dateien fuer den `pricewatch` Agent
- `configs/openclaw.pi.template.json`: bereinigte Template-Konfiguration ohne echte Secrets
- `scripts/deploy-dev.sh`: Deployment nach `~/.openclaw-dev`
- `scripts/deploy-prod.sh`: Deployment nach `~/.openclaw`

## Initiale Nutzung
1. Optional: `cp configs/openclaw.pi.template.json configs/openclaw.dev.local.json` und lokal anpassen.
2. Deploy Dev: `bash scripts/deploy-dev.sh`
3. Deploy Prod: `bash scripts/deploy-prod.sh`

## Sicherheit
- Keine echten API Keys, Tokens oder `auth-state` in Git committen.
- Secrets nur auf dem Raspberry in `~/.openclaw/secrets` oder `~/.openclaw-dev/secrets` halten.
