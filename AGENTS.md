# AGENTS

This repository is the public source version of a Windows desktop automation case study.

## Rules

- Do not commit packaged executables, driver bundles, activation endpoints, local `config.json`, license state, tokens, logs, or audio templates.
- After code changes, run `python -B -m py_compile` on touched Python entrypoints.
- Keep automation changes scoped and explain safety assumptions in README or comments when behavior changes.
- Use `apply_patch` for manual edits.

## Useful Commands

```powershell
python -B -m py_compile .\rock_shiny_auto.py .\rock_shiny_gui.py
python .\rock_shiny_auto.py --list-windows
python .\rock_shiny_auto.py --audio-test
python .\rock_shiny_auto.py --test-guest-f
python .\rock_shiny_auto.py --test-guest-request
python .\rock_shiny_auto.py --test-host-accept
```
