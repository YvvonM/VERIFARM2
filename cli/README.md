# verifarms CLI

A modern command-line client for the VeriFarms verified-claims **Egress API**
(Typer + Rich + HTTPX + Pydantic v2).

## Install

```bash
pip install .            # from the cli/ directory → exposes the `verifarms` command
# or, for development:
pip install -e .
```

## Quickstart

```bash
verifarms auth login                       # prompts for env + base URL + API key (saved 0o600)
verifarms auth status                       # show configured environments (keys masked)

verifarms get claim <claim_id> --format table   # json | text | table
verifarms export organizations --status verified --out orgs.csv
verifarms export claims --claim-type land_size_hectares --out claims.jsonl

verifarms --env production get claim <claim_id>  # switch environment on the fly
```

## Configuration

Stored at `~/.verifarms/config.json` (override with `VERIFARMS_CONFIG_DIR`) with
owner-only `0o600` permissions. One entry per environment; the API token is
injected into the `X-API-Key` header automatically by the client layer.

## Layout

```
verifarms_cli/
├── main.py          # Typer entrypoint + global --env callback (state on ctx.obj)
├── config.py        # Pydantic config; secure (0o600) load/save
├── client.py        # httpx client; auto-injects X-API-Key + base_url
├── formatting.py    # Rich rendering (json/text/table)
├── util.py          # error boundary → friendly messages + exit codes
└── commands/
    ├── auth.py      # auth login / status
    ├── get.py       # get claim
    └── export.py    # export organizations / claims (rich.progress)
```
