# Rock Shiny Auto

A Windows desktop automation case study for a two-window game workflow. The project combines Win32 window control, keyboard/mouse input abstraction, audio-template detection, a Tkinter GUI, and configurable timing/randomization.

This public portfolio version contains source code only. It excludes packaged executables, driver bundles, licensing/admin tooling, local state, activation endpoints, and private release artifacts.

## What It Demonstrates

- Win32 window discovery, focus, resize, and foreground checks.
- Config-driven keyboard/mouse automation.
- Optional Interception-based input backend for games that ignore standard input events.
- Audio monitoring with template matching to stop automation when a target sound appears.
- Tkinter GUI for selecting host/guest windows, speed, cycle count, audio monitoring, and run logs.
- Safety controls: dry-run mode, hotkeys, stop flag, cycle limits, foreground checks, and jittered waits.

## Public Repository Scope

Included:

- `rock_shiny_auto.py` - automation core and CLI tools.
- `rock_shiny_gui.py` - desktop GUI.
- `interception_device_scanner.py` - device discovery helper source.
- `interception_input_tester.py` and `input_method_tester.py` - local diagnostic helpers.
- `config.example.json` - safe local configuration template.
- `requirements.txt` - Python dependencies.

Excluded:

- Packaged `.exe` files and PyInstaller build outputs.
- Third-party driver archives and installer bundles.
- Private activation/license server code and admin tools.
- Local `config.json`, license state, tokens, logs, and audio templates.

## Quick Start

```powershell
python -m pip install -r requirements.txt
Copy-Item .\config.example.json .\config.json
python .\rock_shiny_gui.py
```

CLI checks:

```powershell
python .\rock_shiny_auto.py --list-windows
python .\rock_shiny_auto.py --dry-run --no-audio
python .\rock_shiny_auto.py --hotkey-debug
```

Static syntax check:

```powershell
python -B -m py_compile .\rock_shiny_auto.py .\rock_shiny_gui.py .\interception_device_scanner.py
```

## Notes

This is a learning and portfolio source release. Use automation responsibly and only in workflows where you have authorization.
