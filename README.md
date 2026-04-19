# openclaw-dev

Git-repo fuer versionierbare OpenClaw-Agenten und Workspaces.

## Struktur
- `agents/<id>/agent/`: agent-spezifische OpenClaw-Agent-Configs (ohne Laufzeit-/Auth-State)
- `workspaces/<id>`: Workspace-Dateien je Agent (`main`, `mail`, `pricewatch`, ...)
- `configs/openclaw.pi.template.json`: bereinigte Template-Konfiguration ohne echte Secrets
- `scripts/deploy.sh`: generisches Deployment (`--all` oder `--agent <id>`)
- `scripts/deploy-dev.sh`: Wrapper fuer `deploy.sh --env dev`
- `scripts/deploy-prod.sh`: Wrapper fuer `deploy.sh --env prod`

## Initiale Nutzung
1. Optional: `cp configs/openclaw.pi.template.json configs/openclaw.dev.local.json` und lokal anpassen.
2. Verfuegbare Agenten anzeigen: `bash scripts/deploy.sh --list`
3. Alle Agenten nach Dev deployen: `bash scripts/deploy-dev.sh --all`
4. Einzelnen Agenten nach Dev deployen: `bash scripts/deploy-dev.sh --agent mail`
5. Einzelnen Agenten nach Prod deployen: `bash scripts/deploy-prod.sh --agent mail`

## Hinweise
- Standard-Host ist `msquare@dashboard`, ueberschreibbar via `--host` oder `PI_HOST`.
- Standard-Targets sind `~/.openclaw-dev` (dev) und `~/.openclaw` (prod), ueberschreibbar via `--target`.
- Fuer Agent `main` wird remote `workspace/` genutzt.
- Fuer andere Agenten nutzt das Script automatisch vorhandene Legacy-Pfade `workspace-<id>` oder sonst `workspace/<id>`.

## Sicherheit
- Keine echten API Keys, Tokens oder `auth-state` in Git committen.
- Secrets nur auf dem Raspberry in `~/.openclaw/secrets` oder `~/.openclaw-dev/secrets` halten.
