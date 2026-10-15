# afrp CLI

Command-line client for AFRP CRM Helper. It stores a base URL and API key, then calls the HTTP API.

**Version:** 1.5.0

## Install

```bash
pipx install ./cli
```

## Setup

Create an API key on the Settings page (administrators only), then:

```bash
afrp setup user --name home --base-url http://localhost:5066 --api-key afrp_...
afrp setup test
```

Config is `~/.config/afrp-helper/config.json` (mode 0600).

`AFRP_BASE_URL` and `AFRP_API_KEY` override the saved profile for one command.

## Commands

Every group accepts `-h` / `--help`. An event argument may be the campaign id or a unique name from `afrp seating events`.

| Group | Examples |
|-------|----------|
| Discovery | `afrp help`, `afrp help seating`, `afrp whoami`, `afrp commands`, `afrp openapi -o spec.yaml` |
| Seating | `afrp seating events`, `seating board "Grand Banquet"`, `seating guests EVENT -q jane`, `seating move EVENT --contact ID --table ID` |
| Campaigns | `afrp campaigns list`, `campaigns sub-events CAMPAIGN_ID` |
| Badges | `afrp badges templates`, `badges start --data '{...}'`, `badges job JOB`, `badges download JOB -o badges.pdf` |
| Magazine | `afrp magazine schedules` |

## Update

`afrp update` looks for `cli-vX.Y.Z` tags on GitHub and reinstalls with pipx. `afrp update --check` only prints the versions. `afrp update -y` skips the prompt.

The CLI must already be installed with pipx, and git needs SSH access to the repo (or set `GITHUB_TOKEN`).

Routes without a dedicated command still work:

```bash
afrp call GET /api/avery-templates
afrp call POST /event -d '{"crmUrl":"https://..."}'
```
