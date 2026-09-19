# keyclack

Mechanical-keyboard sound effects on every key press — a [Klack](https://tryklack.com/)-style
daemon for Linux on Wayland (Omarchy / Hyprland / any compositor).

Reads raw `/dev/input` events with `python-evdev`, so it works on Wayland with no compositor
hack or X11 grab, and needs **no root** when your user is in the `input` group. Audio is a
single low-latency PortAudio/PipeWire stream that polyphonically mixes real recorded switch
samples, so fast typing layers naturally instead of cutting each click off.

Ships with real recorded switch packs (MIT-licensed, from the [obsidian-click-clack](https://github.com/Acylation/obsidian-click-clack)
project): Cherry MX Blue / Brown / Red, ALPS-style, IBM, Subtle clicks.

## Install

### Prerequisites
- Linux with `python3` (≥ 3.10) and a PipeWire / PulseAudio server running.
- Your user in the `input` group so `/dev/input` can be read without root:
  ```
  sudo usermod -aG input "$USER"    # log out & back in (or reboot) after this
  ```

### From this repo

```bash
python3 -m venv .venv
.venv/bin/pip install .
# or, with uv:
uv venv && uv pip install .

.venv/bin/keyclack install-packs     # copy bundled sample packs into ~/.local/share/keyclack/packs
.venv/bin/keyclack test              # end-to-end self test (prints PASS + plays audible clicks)
.venv/bin/keyclack run               # run the daemon in the foreground
```

Add the console script to your `PATH` (e.g. `ln -s $(pwd)/.venv/bin/keyclack ~/.local/bin/keyclack`),
or install with `pipx`/a user site. The bundled packs are used as a fallback automatically, so
the app works immediately after `pip install .` even before you run `install-packs`.

> Note: `keyclack` is also the name of the Python package, so run it as a **console script**
> (`.venv/bin/keyclack`), not `python -m keyclack` from an arbitrary directory.

## Usage

| command | what it does |
|---|---|
| `keyclack run` | run the daemon (foreground). `-v` logs keys/peak |
| `keyclack list` | show detected keyboards |
| `keyclack packs` | list available sound packs (`.` = active) |
| `keyclack install-packs` | copy bundled packs into your pack dir (`~/.local/share/keyclack/packs`) |
| `keyclack pack <id>` | switch sound pack live (no restart; persists) |
| `keyclack next-pack` | cycle to the next installed pack (live) |
| `keyclack soundcheck` | play each sample of the active pack once (audio check) |
| `keyclack test` | end-to-end test (virtual typing -> capture -> audio) |
| `keyclack toggle` | mute/unmute a running daemon (SIGUSR1) |
| `keyclack state` | machine-readable state: `running enabled pack=<id> volume=0.9 (pid N)` |
| `keyclack status` | is the daemon running? |
| `keyclack set volume=0.6` | change settings (also `pack=...`, `enabled=...`, `devices=...`) |

### Autostart at login (like Klack always running)

Hyprland — add to `~/.config/hypr/autostart.lua`:

```lua
o.launch_on_start("keyclack run")
```

> The `run` subcommand is required — a bare `keyclack` only prints usage.

Other compositors — add `keyclack run` to your normal session-autostart mechanism.

## Configuration

Everything lives in `~/.config/keyclack/config.toml` (auto-created on first run):

- `pack` — which sound pack (see `keyclack packs`).
- `volume` — 0.0–1.0.
- `devices` — `"auto"` (all real keyboards) or a list like `["Keychron", "event2"]`
  to filter. Synthetic keyboards (e.g. Logitech's virtual `solaar-keyboard`) are always skipped.
- `play_on_repeat` — play on held-key auto-repeat (default `false`).
- `include_modifiers` — Shift/Ctrl/Alt/Super also click (default `true`).
- `audio_device`, `sample_rate`, `pack_dir`.

Pack directories are searched in this order: your `pack_dir`, then the packs bundled with the
package. Drop custom packs into `~/.local/share/keyclack/packs/<name>/` (each is a folder with a
`manifest.json` mapping roles like `key`, `key2`, `enter`, `space`, `delete` to sample files).

## How it works

```
keyboard ──(/dev/input, evdev)── Capture threads ──> KeyRoles (per-key role)
                                                        │
                          low-latency PipeWire stream ◄─┘ polyphonic Mixer
                                                        │
                                                     🔊 speakers
```

Only the *press* (evdev value 1) is sounded, so holding a key down doesn't machine-gun.
Generic keys alternate between the pack's `key`/`key2` samples so typing has texture rather
than one identical click looping.

## Omarchy plugin (bar widget + settings panel)

This repository is also an [Omarchy](https://omarchy.org/) shell plugin
(`pranav.keyclack`). A keyboard glyph in the top bar shows the daemon's live
state: **left click** opens a settings panel (volume slider, sound-pack
picker, mute), **right click** mutes/unmutes, **middle click** cycles the
sound pack.

### Install (Omarchy)

1. Install the daemon and make sure `keyclack` is on your `PATH`:
   ```bash
   sudo pacman -S --needed portaudio      # system audio lib for sounddevice
   uv tool install git+https://github.com/pranavchavda/keyclack.git
   # or: pipx install git+https://github.com/pranavchavda/keyclack.git
   ```
2. Add your user to the `input` group (see Prerequisites above), then install
   the plugin:
   ```bash
   omarchy plugin add https://github.com/pranavchavda/keyclack.git --enable
   ```
3. Autostart the daemon (see above), or just click the bar icon and press
   **Start**.

The widget resolves the `keyclack` CLI from your `PATH` at runtime, so any
install method works.

### Remove (Omarchy)

```bash
omarchy plugin remove pranav.keyclack
uv tool uninstall keyclack        # or pipx uninstall keyclack
# remove the o.launch_on_start("keyclack run") line from ~/.config/hypr/autostart.lua
rm -rf ~/.config/keyclack ~/.local/share/keyclack    # settings + sample packs
```

### Dependencies

- **Python** ≥ 3.10 — declared in `pyproject.toml`: `evdev`, `sounddevice`,
  `soundfile`, `numpy` (installed automatically by pipx / uv).
- **System**: `portaudio` (PipeWire/PulseAudio setups provide the server).
  Optional: writable `/dev/uinput` for `keyclack test` (comes with the
  `input` group).
- **License**: MIT — this repo and the bundled sample packs (see
  [THIRD_PARTY.md](THIRD_PARTY.md)).

## License

MIT © 2026 Pranav Chavda. Sample packs are MIT-licensed from obsidian-click-clack — see
[THIRD_PARTY.md](THIRD_PARTY.md).
