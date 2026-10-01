# Plan 002: Make the README install command actually work

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat b655bb3..HEAD -- README.md`
> If README.md changed since this plan was written, compare the "Current
> state" excerpt against the live file before proceeding; on a mismatch,
> treat it as a STOP condition. (Plan 001 appends a "Development" section;
> that change is expected and is not drift.)

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: docs
- **Planned at**: commit `b655bb3`, 2026-10-01

## Why this matters

The README's Installation section tells users to run `inkypi install ...`.
InkyPi's CLI has no `install` subcommand. Its dispatcher (InkyPi
`install/inkypi`) only accepts `run` and `plugin`, and anything else prints
`Unknown command: install` and exits 1. Plugin installs go through
`inkypi plugin install <plugin_id> <git_repository_url>` (InkyPi
`install/cli/inkypi-plugin`). The first command every new user runs therefore fails.

## Current state

`README.md:28-33`:

````markdown
## Installation

Install the plugin using the InkyPi CLI:

```bash
inkypi install isolarcloud https://github.com/jordauld1/InkyPi-iSolarCloud
```
````

InkyPi's CLI dispatcher, for reference (InkyPi `install/inkypi`):

```bash
case "$command" in
    run)
        run_app
        ;;
    plugin)
        run_plugin_cli "$@"
        ;;
    ...
    *)
        echo "Unknown command: $command"
```

InkyPi's plugin CLI usage text (InkyPi `install/cli/inkypi-plugin:12-14`):

```
  inkypi plugin install <plugin_id> <git_repository_url>
  inkypi plugin uninstall <plugin_id>
  inkypi plugin list
```

`inkypi plugin install` deletes the plugin folder and re-clones it, so the
same command also updates the plugin.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Check old command gone | `grep -n "inkypi install" README.md` | no output, exit 1 |
| Check new command present | `grep -n "inkypi plugin install isolarcloud" README.md` | 1 match |

## Scope

**In scope**: `README.md` (the Installation section only).

**Out of scope**: every other README section, and all code.

## Git workflow

- Branch: `advisor/002-readme-install`
- One commit: `Fix README install command (inkypi plugin install)`
- Do NOT push unless instructed.

## Steps

### Step 1: Replace the Installation section body

Replace the README's Installation section with exactly:

````markdown
## Installation

Install the plugin using the InkyPi CLI:

```bash
inkypi plugin install isolarcloud https://github.com/jordauld1/InkyPi-iSolarCloud
```

Run the same command again to update to the latest version. To remove it:

```bash
inkypi plugin uninstall isolarcloud
```
````

**Verify**: `grep -n "inkypi install" README.md` → no output;
`grep -c "inkypi plugin install isolarcloud" README.md` → `1`;
`grep -c "inkypi plugin uninstall isolarcloud" README.md` → `1`.

## Test plan

Docs only; no tests.

## Done criteria

- [ ] Both greps above give the expected results
- [ ] `git diff --stat` shows only `README.md` changed (plus `plans/README.md`)
- [ ] `plans/README.md` row 002 updated

## STOP conditions

- The Installation section no longer matches the excerpt (for example, someone already fixed it). Report and mark the plan REJECTED with that reason.

## Maintenance notes

- If InkyPi renames its CLI again, this is the only place to update. The
  repository URL also appears in `isolarcloud/plugin-info.json` and must stay
  identical.
