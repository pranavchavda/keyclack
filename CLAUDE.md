# CLAUDE.md

Guidance for AI agents (Claude Code, Codex, Hermes, etc.) and humans working on this repo.

## What this is

`keyclack` plays real recorded mechanical-switch samples on every key press (a
[Klack](https://tryklack.com/)-style daemon) for Linux/Wayland. It reads `/dev/input`
via `python-evdev` (no X11 grab, no root when the user is in the `input` group) and mixes
low-latency audio through one polyphonic PortAudio/PipeWire stream.

## Repository layout

```
keyclack/                     Python package (the daemon + CLI)
  config.py                   Config file, XDG paths, bundled-pack fallback logic
  capture.py                  Device discovery (evdev) + reader threads
  roles.py                    Maps raw keycodes -> sound roles (key/key2/space/enter/delete)
  audio.py                    Sample-pack loader (Pack) + polyphonic mixing engine
  uinput_tools.py             Virtual-keyboard injection for `keyclack test`
  main.py                     CLI + daemon entry (argparse, signals, commands)
  packs/                      Bundled sample packs (MIT, from obsidian-click-clack)
  __init__.py, __main__.py
omarchy/pranav.keyclack/      Optional Omarchy/Quickshell bar widget (separate component)
bin/keyclack                  Legacy launcher (local dev convenience; console script is canonical)
pyproject.toml                Packaging + `keyclack` console-script entry point
LICENSE, THIRD_PARTY.md, README.md, CONTRIBUTING.md, CLAUDE.md
```

The Python package and the Omarchy widget are **two separate concerns**. Changes to the
daemon do not require a shell restart; changes to the widget do (see below).

## Commands that matter

```bash
keyclack run               # foreground daemon
keyclack test              # end-to-end self test (uinput virtual typing -> capture -> audio)
keyclack soundcheck        # plays each sample of the active pack
keyclack packs             # lists available packs; marks the active one
keyclack install-packs     # copies bundled packs into ~/.local/share/keyclack/packs
keyclack pack <id>         # live-swap pack (writes config + SIGUSR2 to running daemon)
keyclack toggle            # mute/unmute running daemon (SIGUSR1)
keyclack state             # machine-readable: running enabled pack=<id> (pid N)
```

`keyclack test` is the main verification gate — always run it after touching capture, audio,
roles, or pack loading. It needs write access to `/dev/uinput`.

## Hard-won gotchas (do not re-break these)

1. **`keyclack` requires a subcommand** — the CLI's subparser is `required=True`. A bare
   `keyclack` just prints usage and exits (exit 120). Autostart/systemd/bar launch lines MUST
   say `keyclack run`, never bare `keyclack`. This bit us once: a reboot autostart silently
   failed because the line was `o.launch_on_start("keyclack")` instead of `"keyclack run"`.

2. **`python -m keyclack` only works from the project root.** The module isn't installed as a
   package in dev. Always run via the console script (`.venv/bin/keyclack`) or after
   `pip install -e .`. Systemd / autostart / bar launches run from a different cwd.

3. **Quickshell `Process` does NO PATH lookup on a bare `argv[0]`** and does not expand
   `$HOME`. In any widget that shells out, use an absolute path to the binary (see
   `omarchy/pranav.keyclack/BarWidget.qml` `exe`), and remember `bar.run()` goes through
   `bash -lc` while `Process` does not — they behave differently.

4. **`omarchy-shell shell rescanPlugins` reloads the plugin list but NOT edited widget code.**
   After editing a bar widget, do a full `omarchy restart shell`.

5. **Pack loading has a bundled fallback.** `keyclack/config.py` `pack_dirs()` /
   `find_pack_dir()` / `list_available_packs()` search the user dir (`pack_dir`, default
   `~/.local/share/keyclack/packs`) first, then the packaged `keyclack/packs/`.
   `Config.resolve_pack_path()` is the one entry point — don't construct pack paths directly.

6. **Licensing is deliberate.** Bundled sample packs are MIT from
   [obsidian-click-clack](https://github.com/Acylation/obsidian-click-clack). Keep the
   attribution in `THIRD_PARTY.md`; only add packs you have rights to redistribute.

7. **Only the key *press* (evdev value 1) is sounded**, not auto-repeat — by design, so
   holding a key doesn't machine-gun.

8. **Keyboards hotplug; never assume the startup snapshot is complete.** Bluetooth boards
   connect after the daemon starts and reconnect after every sleep. The daemon loop calls
   `Capture.rescan()` every 2s to open new devices and close gone ones (see `capture.py`);
   `tests/test_hotplug.py` guards this. Code that lists or opens `/dev/input` devices must
   go through `Capture`, not enumerate once itself.

9. **`keyclack set volume=…` / `pack` apply live.** `cmd_set` writes config then signals
   the daemon with SIGUSR2 for hot-reloadable keys (volume, pack) — same contract as
   `keyclack pack`. The Omarchy settings panel relies on this; never make the panel talk
   to the daemon directly, always go through the CLI.

10. **The bar widget MUST define `open()`/`close()`/`toggle()`.** `Ui.KeyboardPanel`'s
    outside-click/Esc dismissal calls `owner.close()`; if the host `BarWidget` lacks it,
    KeyboardPanel assigns its own `open` directly, permanently breaking the
    `open: root.opened` binding — the icon toggles red but the panel never maps again
    (bit us: "left click doesn't open the gui"). Debug live wiring with
    `quickshell ipc -p /usr/share/omarchy/shell call pranav.keyclack diag`.

## Conventions

- **Signals**: SIGUSR1 = mute/unmute toggle; SIGUSR2 = reload pack from config (hot swap,
  audio keeps running). Keep new daemon controls on new signals, never over thread-state.
- **Config is the source of truth** for pack/volume/devices; `keyclack pack` writes config then
  signals the daemon. Runtime state (muted/enabled) is separate and lives in the pid/state
  files under `$XDG_RUNTIME_DIR`.
- Code style: PEP 8, type hints on public signatures, docstrings on modules/classes. QML
  follows the Omarchy house style (see `world-clock`/`microphone` widgets in an omarchy install).
- Never commit `.venv/`, `__pycache__/`, or local absolute paths (except the deliberately
  per-machine `exe` in the example widget, which is clearly marked to edit).
- New sample packs must follow the pack format: a folder with `manifest.json` mapping roles
  (`key`, `key2`, `enter`, `space`, `delete`) to sample files, plus the audio files themselves.

## Roadmap context (v0.2)

Planned: original switch recordings contributed by the maintainer (Gateron Blacks from a Wuque
Studio Ginkgo65), a systemd user unit for non-Hyprland sessions, and a release tag. Keep this
repo single-purpose and approachable for contributors.
