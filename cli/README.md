# afrp CLI

Command-line client for AFRP CRM Helper. It stores a base URL and API key, then calls the HTTP API.

**Version:** 1.6.1

## Install

```bash
pipx install "git+https://github.com/rgnet1/AFRP-Helper-Functions.git@cli-v1.6.1#subdirectory=cli"
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
| Registration | `afrp registration events`, `registration search --email jane@example.com --campaign ID`, `registration add --campaign ID --event ID --contact ID --skip-payment` |
| Membership | `afrp membership years`, `membership lookup --contact ID --year 2026`, `membership purchase --contact ID --year 2026 --plan CONTACT:CATEGORY --skip-payment` |
| Password | `afrp password search --email jane@example.com`, `password set --contact ID --password '...'` |
| Campaigns | `afrp campaigns list`, `campaigns sub-events CAMPAIGN_ID` |
| Badges | `afrp badges templates`, `badges sizes`, `badges preprocessing`, `badges meals --campaign ID`, `badges start --data '{...}'`, `badges job JOB`, `badges download JOB -o badges.pdf` |
| Magazine | `afrp magazine schedules`, `magazine create --frequency daily --time "09:30 AM"`, `magazine delete ID` |
| QR | `afrp qr make "hello" -o qr.png` |
| Event URL | `afrp event url "https://afrp.crm.dynamics.com/..."` |

A sign-up or membership that has a price returns `payment_required` unless you pass `--skip-payment`. Card checkout stays on the website. The key only sees features that account is allowed to open.

## Update

`afrp update` looks for `cli-vX.Y.Z` tags on GitHub and reinstalls with pipx. `afrp update --check` only prints the versions. `afrp update -y` skips the prompt.

The CLI must already be installed with pipx. Updates install over HTTPS from the public GitHub repo.

Routes without a dedicated command still work:

```bash
afrp call GET /api/avery-templates
afrp call POST /event -d '{"crmUrl":"https://..."}'
```
