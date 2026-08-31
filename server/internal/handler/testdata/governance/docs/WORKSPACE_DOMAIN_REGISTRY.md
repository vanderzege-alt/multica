# Workspace Domain Registry

**Status:** living SSOT (open registry — not a closed catalog)  
**Epic:** VAN-131 §2.1  
**Owner:** Mika (registry PRs) + Founder sign-off on new `active` slugs

Each row: `slug | kind | status | Multica Project | charter path`

| slug | kind | status | Multica Project | charter path |
|------|------|--------|-----------------|--------------|
| parallel-reader | product | active | | |
| multica | platform | active | | |
| hermes | platform | active | | |
| gauntlet | service | active | | |
| nl-taal | product | paused | | |
| gov | platform-cross | active | | |
| infra | platform-cross | active | | |
| agents | platform-cross | active | | |

## Status meanings

| status | Meaning |
|--------|---------|
| **active** | slug allowed for epic/feature in `todo` / `in_progress` |
| **paused** | work frozen (epic only `backlog`); e.g. `nl-taal` |
| **proposed** | idea registered, charter not ready — only `backlog` issues |

## Kinds

| kind | Description |
|------|-------------|
| **product** | User-facing offering |
| **platform** | Internal platform other work builds on |
| **service** | Shared ecosystem service |
| **platform-cross** | Cross-cutting engineering domain (`gov`, `infra`, `agents`) |

## Registration workflow

1. `backlog` issue `gov(registry): register domain <slug>` with kind + 1-paragraph intent.
2. Mika adds a `proposed` row here (PR in governance).
3. S0 charter stub → status `active`.
4. `epic(<slug>):` titles become mechanically valid (P1b blocking gates).
