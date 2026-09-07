# Contributing to keyclack

Thanks for wanting to help make everyone's keyboard sound better. This project is small and
friendly — a Klack-style daemon for Linux/Wayland that plays real recorded mechanical-switch
samples on every key press.

## Project health

- **License:** MIT. All contributions are assumed MIT-licensed.
- **Sample packs** bundled in the repo are MIT from
  [obsidian-click-clack](https://github.com/Acylation/obsidian-click-clack) — keep the
  attribution in `THIRD_PARTY.md`. Only add packs/recordings you have the right to redistribute.
- Agents working here should read `AGENTS.md` first (layout, commands, and hard-won gotchas).

## Getting set up

Requires Python ≥ 3.10, a running PipeWire/PulseAudio server, and your user in the `input`
group (for rootless `/dev/input` reads) plus write access to `/dev/uinput` for the self-test:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .            # or: uv venv && uv pip install -e .
.venv/bin/keyclack install-packs      # copy bundled packs into ~/.local/share/keyclack/packs
.venv/bin/keyclack test               # end-to-end self test (prints PASS + audible clicks)
.venv/bin/keyclack run                # foreground daemon
```

Use the **console script** (`.venv/bin/keyclack`), not `python -m keyclack` from an arbitrary
directory — the module only imports from the project root.

## Development loop

1. Make your change.
2. Run `keyclack test` — it is the main verification gate (virtual typing → capture → audio).
   It must print `RESULT: PASS`.
3. For audio/pack work, `keyclack soundcheck` plays each sample of the active pack so you can
   hear what changed.
4. Run `python -m py_compile keyclack/*.py` (or your linter) to catch syntax errors.

## Project layout

```
keyclack/        Python package (daemon + CLI)
  capture.py     evdev device discovery + reader threads
  roles.py       keycode -> sound role mapping
  audio.py       sample-pack loader + polyphonic mixing engine
  config.py      config + XDG paths + bundled-pack fallback
  main.py        CLI + daemon entry (signals: SIGUSR1 mute, SIGUSR2 pack reload)
  uinput_tools.py virtual keyboard for the self-test
  packs/         bundled sample packs
omarchy/pranav.keyclack/   optional Omarchy/Quickshell bar widget (separate component)
```

Keep the Python daemon and the shell widget as separate concerns — a daemon change doesn't
need a shell restart, but a widget change does (`omarchy restart shell`).

## Adding a sound pack

Each pack is a folder containing a `manifest.json` plus audio files:

```json
{
  "id": "my-switch",
  "caption": "My Switch",
  "key": "key.wav",
  "key2": "key2.wav",
  "enter": "enter.wav",
  "space": "space.wav",
  "delete": "delete.wav"
}
```

- Audio files: mono/stereo WAV preferred, decoded with `soundfile`; loaded mono and resampled
  to the output rate. Short percussive samples (~40–120 ms) work best.
- To try a pack, drop the folder into `~/.local/share/keyclack/packs/<id>/` and
  `keyclack pack <id>`.
- To contribute it: add the folder under `keyclack/packs/<id>/`, confirm you may redistribute
  it under MIT, and note the source if it isn't your own recording.

## Recording quality (for original switch recordings)

Good keyboard recordings are dry and close-mic'd: record on a clean surface, no room reverb,
no background hum, one keypress per take, and normalize. Keep the natural attack — that's the
"clack". If you can, record each role (`key`, `space`, `enter`, `delete`) and two generic
variants (`key` / `key2`) for typing texture.

## Code style

- **Python:** PEP 8, type hints on public functions, short docstrings. Match the surrounding code.
- **QML** (widget only): follow Omarchy's house style — base everything on `BarWidget`,
  reference the binary by absolute path (`Process` has no PATH lookup), poll via a `Process` +
  `StdioCollector`, and use `BarIconButton` with Font Awesome glyph codepoints.
- Keep changes focused. If a PR bundles three unrelated ideas, split it.

## Submitting changes

1. Fork the repo and open a PR against `main`.
2. Title it clearly; describe what and why, and note how you tested (`keyclack test` result).
3. Small, reviewable diffs are very welcome. Big feature ideas? Open an issue first so we align.

## First-time contributor?

A great first issue is often one of: a new sound pack, a non-Hyprland/systemd autostart unit,
better `keyclack test` diagnostics, or wider audio-device handling. Check the open issues.
