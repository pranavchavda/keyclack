"""keyclack command-line interface.

Commands
    keyclack run            run the daemon in the foreground
    keyclack list           list detected keyboard devices
    keyclack packs          list installed sound packs
    keyclack soundcheck     play each sample of the active pack (audio test)
    keyclack test           end-to-end self test (injects virtual typing)
    keyclack toggle         toggle sound on/off for a running daemon (SIGUSR1)
    keyclack status         is a daemon running?
    keyclack set k=v ...    write settings to config (volume, pack, ...)
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time

from . import APP, __version__
from . import audio as audio_mod
from .audio import AudioEngine, Pack
from .capture import Capture, discover_keyboards
from .config import (Config, CONFIG_FILE, ensure_defaults,
                     find_pack_dir, list_available_packs, BUNDLED_PACK_DIR)
from .roles import KeyRoles, key_name

# --------------------------------------------------------------------------
# runtime / control
# --------------------------------------------------------------------------

def _pidfile() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return os.path.join(runtime, f"{APP}.{os.getuid()}.pid")


class _State:
    def __init__(self):
        self.enabled = True
        self.volume = 1.0
        self.keys = 0
        self.roles = {}  # role -> count


STATE = _State()


def _on_key(code: int, value: int, name: str, engine: AudioEngine,
            pack: Pack, roles: KeyRoles) -> None:
    if not STATE.enabled:
        return
    role = roles.resolve(code)
    if role is None:
        return
    STATE.keys += 1
    engine.play_role(pack, role)


# --------------------------------------------------------------------------
# daemon
# --------------------------------------------------------------------------

def cmd_run(cfg: Config, verbose: bool = False) -> int:
    ensure_defaults()
    # Singleton guard: refuse to start if another daemon is already running,
    # so autostart on a fresh login can't stack a second instance (which
    # would double every keystroke).
    existing = _daemon_pid()
    if existing is not None:
        print(f"keyclack: already running (pid {existing}). "
              f"Use `keyclack toggle` to mute, or stop it first.", file=sys.stderr)
        return 2
    pack_path = cfg.resolve_pack_path()
    if pack_path is None:
        print("keyclack: could not locate sound pack "
              f"'{cfg.pack}' in pack dirs. Run `keyclack packs`.",
              file=sys.stderr)
        return 2
    try:
        pack = Pack(pack_path, cfg.sample_rate)
    except Exception as exc:
        print(f"keyclack: could not load pack '{cfg.pack}': {exc}", file=sys.stderr)
        return 2

    STATE.enabled = cfg.enabled
    STATE.volume = cfg.volume

    roles = KeyRoles(include_modifiers=cfg.include_modifiers)
    engine = AudioEngine(device=cfg.audio_device,
                         sample_rate=cfg.sample_rate, volume=cfg.volume)
    holder = {"pack": pack}  # mutable so SIGUSR2 can hot-swap the pack
    cap = None
    try:
        engine.start()

        def on_key(code, value, name):
            _on_key(code, value, name, engine, holder["pack"], roles)

        cap = Capture(handler=on_key, play_on_repeat=cfg.play_on_repeat)
        nstarted = cap.start(cfg.devices)
        if not nstarted:
            print("keyclack: no keyboard devices found. "
                  "Are you in the 'input' group? (a reboot is needed after "
                  "adding yourself to it)", file=sys.stderr)

        print(f"keyclack {__version__}  pack='{pack.caption}'  "
              f"device='{cfg.audio_device}'  volume={cfg.volume}")
        for line in cap.opened:
            print(f"  listening: {line}")
        print("ready. type to hear it.  SIGUSR1 toggles sound, Ctrl-C quits.")

        _write_pid()
        _write_state()
        stop = {"flag": False}

        def _term(signum, frame):
            stop["flag"] = True

        def _usr1(signum, frame):
            STATE.enabled = not STATE.enabled
            _write_state()
            print(f"\nkeyclack: {'ENABLED' if STATE.enabled else 'MUTED'}")

        def _usr2(signum, frame):
            # Hot-swap the sound pack: re-read the config (the CLI just wrote
            # a new `pack`) and reload only the samples - audio keeps running.
            try:
                fresh = Config.load()
                new_path = fresh.resolve_pack_path()
                if new_path is None:
                    raise FileNotFoundError(f"pack '{fresh.pack}' not found")
                new_pack = Pack(new_path, fresh.sample_rate)
            except Exception as exc:
                print(f"\nkeyclack: pack reload failed: {exc}", file=sys.stderr)
            old_caption = holder["pack"].caption
            holder["pack"] = new_pack
            if fresh.volume != STATE.volume:
                STATE.volume = fresh.volume
                engine.volume = fresh.volume
                print(f"\nkeyclack: volume -> {fresh.volume}")
            if new_pack.caption != old_caption:
                print(f"\nkeyclack: pack -> '{new_pack.caption}'")
            _write_state()

        signal.signal(signal.SIGINT, _term)
        signal.signal(signal.SIGTERM, _term)
        signal.signal(signal.SIGUSR1, _usr1)
        signal.signal(signal.SIGUSR2, _usr2)

        last_t = time.time()
        last_scan = time.time()
        while not stop["flag"]:
            time.sleep(0.25)
            now = time.time()
            # Hotplug: keyboards connect and reconnect after startup
            # (Bluetooth boards pair late, sleep, wake). Reconcile the open
            # device set every couple of seconds so they are picked up
            # without a daemon restart.
            if now - last_scan >= 2.0:
                last_scan = now
                added, removed = cap.rescan(cfg.devices)
                for line in added:
                    print(f"  listening: {line}", flush=True)
                for line in removed:
                    print(f"  released: {line}", flush=True)
            if verbose and now - last_t >= 2.0:
                peak = engine.peak_since()
                print(f"  keys={STATE.keys} peak={peak:.3f}", flush=True)
                last_t = now
    finally:
        if cap:
            cap.stop()
        engine.stop()
        _remove_pid()
        _remove_state()
        print("keyclack: stopped")
    return 0


def _write_pid() -> None:
    try:
        with open(_pidfile(), "w") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass


def _remove_pid() -> None:
    try:
        os.unlink(_pidfile())
    except OSError:
        pass


def _statefile() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return os.path.join(runtime, f"{APP}.{os.getuid()}.state")


def _write_state() -> None:
    """Persist current runtime state for `keyclack status` / bar widgets."""
    try:
        with open(_statefile(), "w") as fh:
            fh.write("enabled\n" if STATE.enabled else "muted\n")
    except OSError:
        pass


def _remove_state() -> None:
    try:
        os.unlink(_statefile())
    except OSError:
        pass


def _daemon_pid() -> int | None:
    """Return the live pid of a running daemon, or None."""
    try:
        with open(_pidfile()) as fh:
            pid = int(fh.read().strip())
    except (FileNotFoundError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return None
    return pid


# --------------------------------------------------------------------------
# informational / helper commands
# --------------------------------------------------------------------------

def cmd_list() -> int:
    kbds = discover_keyboards()
    if not kbds:
        print("no keyboards detected")
        return 0
    for path, name, phys in kbds:
        print(f"{path}  {name}" + (f"  (phys: {phys})" if phys else ""))
    return 0


def _resolve_pack(cfg: Config) -> Pack | None:
    path = cfg.resolve_pack_path()
    if path is None:
        return None
    return Pack(path, cfg.sample_rate)

def cmd_packs(cfg: Config, as_json: bool = False) -> int:
    avail = list_available_packs(cfg.pack_dir)
    if not avail:
        if as_json:
            print("[]")
        else:
            print("no packs found (see pack_dir in the config, "
                  "and `keyclack install-packs`)")
        return 0
    active = cfg.pack
    if as_json:
        rows = []
        for n, path in avail.items():
            cap = ""
            try:
                cap = Pack(path, cfg.sample_rate).caption
            except Exception:
                pass
            rows.append({"id": n, "caption": cap, "active": n == active})
        print(json.dumps(rows))
        return 0
    for n, path in avail.items():
        mark = "  <-- active" if n == active else ""
        cap = ""
        try:
            cap = Pack(path, cfg.sample_rate).caption
        except Exception:
            pass
        src = "(bundled)" if path == os.path.abspath(BUNDLED_PACK_DIR) else ""
        print(f"{n:24} {cap}{' ' + src if src else ''}{mark}")
    return 0


def cmd_soundcheck(cfg: Config) -> int:
    pack = _resolve_pack(cfg)
    if pack is None:
        print(f"keyclack: pack '{cfg.pack}' not found", file=sys.stderr)
        return 1
    print(f"playing samples of pack '{pack.caption}':")
    with AudioEngine(device=cfg.audio_device, sample_rate=cfg.sample_rate,
                     volume=1.0) as engine:
        engine.start()
        for role in ("key", "key2", "space", "enter", "delete"):
            if role in pack.samples:
                print(f"  {role}: {pack.samples[role].size/ cfg.sample_rate*1000:.0f}ms")
                engine.play_role(pack, role)
                time.sleep(max(0.15, pack.samples[role].size / cfg.sample_rate))
        time.sleep(0.3)
    return 0


def cmd_test(cfg: Config) -> int:
    """End-to-end test: attach capture, inject virtual typing, verify audio."""
    pack = _resolve_pack(cfg)
    if pack is None:
        print(f"keyclack: pack '{cfg.pack}' not found", file=sys.stderr)
        return 1
    roles = KeyRoles(include_modifiers=True)
    phrase = "hello world 1234"
    with AudioEngine(device=cfg.audio_device, sample_rate=cfg.sample_rate,
                     volume=1.0) as engine:
        engine.start()
        _on = lambda c, v, n: _on_key(c, v, n, engine, pack, roles)
        # open the virtual keyboard FIRST so capture discovers it, then start
        # capture, then type.
        from .uinput_tools import TypingKeyboard
        tk = TypingKeyboard(phrase)
        try:
            time.sleep(0.3)
            cap = Capture(handler=_on, play_on_repeat=False,
                          include_synthetic=True)
            n = cap.start(cfg.devices)
            print(f"listening on {n} keyboard device(s):")
            for line in cap.opened:
                print(f"  {line}")
            time.sleep(0.4)
            print(f'injecting virtual typing: "{phrase}"')
            before = STATE.keys
            tk.type(phrase, delay=0.05)
            time.sleep(0.8)
            peak = engine.peak_since()
            seen = STATE.keys - before
            ok = seen >= 5 and peak > 0.001
            print(f"\nkeys heard={seen}  audio peak={peak:.4f}")
            print("RESULT:", "PASS  (keys captured and audio produced)"
                  if ok else "CHECK  (see messages above)")
        finally:
            tk.close()
            if "cap" in locals() and cap:
                cap.stop()
        engine.stop()
    return 0 if ok else 1


def _list_pack_ids(cfg: Config) -> list:
    return sorted(list_available_packs(cfg.pack_dir))


def cmd_install_packs(cfg: Config) -> int:
    """Copy the bundled packs into the user-writable pack_dir so the user can
    customize/add packs without them being wiped on a package upgrade."""
    import shutil
    target = os.path.abspath(os.path.expanduser(cfg.pack_dir))
    bundled = os.path.abspath(BUNDLED_PACK_DIR)
    avail = list_available_packs(bundled) if os.path.isdir(bundled) else {}
    if not avail:
        print("no bundled packs to install")
        return 1
    os.makedirs(target, exist_ok=True)
    n = 0
    for name, src in avail.items():
        dst = os.path.join(target, name)
        if os.path.isdir(dst):
            print(f"  {name}: exists, skipped")
            continue
        shutil.copytree(src, dst)
        print(f"  {name}: installed")
        n += 1
    if n:
        print(f"installed {n} pack(s) into {target}")
    return 0


def _signal_daemon(signum: int) -> None:
    pid = _daemon_pid()
    if pid is not None:
        os.kill(pid, signum)


def _set_pack_and_reload(cfg: Config, pack_id: str) -> int:
    """Persist a pack choice and hot-swap the running daemon to it."""
    ids = _list_pack_ids(cfg)
    if pack_id not in ids:
        print(f"keyclack: unknown pack '{pack_id}'. Installed: "
              + (", ".join(ids) if ids else "(none)"))
        return 1
    cfg.pack = pack_id
    cfg.save()
    if _daemon_pid() is not None:
        os.kill(_daemon_pid(), signal.SIGUSR2)  # live reload, no restart
    print(f"pack -> {pack_id}")
    return 0


def cmd_pack(cfg: Config, pack_id: str) -> int:
    return _set_pack_and_reload(cfg, pack_id)


def cmd_next_pack(cfg: Config) -> int:
    ids = _list_pack_ids(cfg)
    if not ids:
        print("keyclack: no packs installed")
        return 1
    try:
        idx = ids.index(cfg.pack)
    except ValueError:
        idx = -1
    nxt = ids[(idx + 1) % len(ids)]
    return _set_pack_and_reload(cfg, nxt)


def _read_state() -> str | None:
    try:
        with open(_statefile()) as fh:
            return fh.read().strip()
    except (FileNotFoundError, OSError):
        return None


def cmd_toggle() -> int:
    pid = _daemon_pid()
    if pid is None:
        print("keyclack: daemon not running")
        return 1
    os.kill(pid, signal.SIGUSR1)
    print(f"toggled daemon pid {pid}")
    return 0


def cmd_state() -> int:
    pid = _daemon_pid()
    if pid is None:
        print("not-running")
        return 1
    state = _read_state() or ("enabled" if STATE.enabled else "muted")
    cfg = Config.load()
    print(f"running {state} pack={cfg.pack} volume={cfg.volume} (pid {pid})")
    return 0


def cmd_status() -> int:
    pid = _daemon_pid()
    if pid is None:
        print("not running")
        return 1
    state = _read_state() or "enabled"
    print(f"running ({state}, pid {pid})")
    return 0


def cmd_set(cfg: Config, pairs: list[str]) -> int:
    hot = False  # keys the running daemon hot-reloads on SIGUSR2
    for pair in pairs:
        if "=" not in pair:
            print(f"expected key=value, got: {pair}")
            return 1
        k, _, v = pair.partition("=")
        k = k.strip().lower()
        v = v.strip()
        if k == "volume":
            cfg.volume = float(v)
            hot = True
        elif k == "pack":
            cfg.pack = v
            hot = True
        elif k == "enabled":
            cfg.enabled = v.lower() in ("1", "true", "yes", "on")
        elif k in ("include_modifiers", "play_on_repeat"):
            setattr(cfg, k, v.lower() in ("1", "true", "yes", "on"))
        elif k == "device" or k == "audio_device":
            cfg.audio_device = v
        elif k == "devices":
            cfg.devices = "auto" if v in ("auto", "*") else [x.strip()
                                                             for x in v.split(",")]
        else:
            print(f"unknown setting '{k}'")
            return 1
        print(f"  {k} = {v}")
    cfg.save()
    print(f"wrote {cfg._path}")
    if hot and _daemon_pid() is not None:
        os.kill(_daemon_pid(), signal.SIGUSR2)  # live reload, no restart
        print("signalled running daemon")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=APP, description=__doc__.splitlines()[0])
    p.add_argument("--version", action="version", version=APP + " " + __version__)
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="run the daemon (foreground)")
    r.add_argument("-v", "--verbose", action="store_true")
    r.add_argument("--volume", type=float, default=None)
    r.add_argument("--pack", default=None)
    r.add_argument("--device", default=None)

    sub.add_parser("list", help="list detected keyboards")
    pl = sub.add_parser("packs", help="list installed sound packs")
    pl.add_argument("--json", action="store_true",
                    help="machine-readable list for scripts/widgets")
    sub.add_parser("install-packs",
                   help="copy bundled packs into your pack dir")
    sub.add_parser("soundcheck", help="play each sample of the active pack")
    sub.add_parser("test", help="end-to-end self test")
    sub.add_parser("toggle", help="toggle sound for the running daemon")
    sub.add_parser("state", help="print daemon state (running enabled/muted)")
    sub.add_parser("status", help="is the daemon running?")
    pk = sub.add_parser("pack", help="set the sound pack (live)")
    pk.add_argument("id")
    sub.add_parser("next-pack", help="cycle to the next installed sound pack")
    s = sub.add_parser("set", help="write settings to config")
    s.add_argument("pairs", nargs="+")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config.load()

    if args.command == "list":
        return cmd_list()
    if args.command == "packs":
        return cmd_packs(cfg, as_json=args.json)
    if args.command == "install-packs":
        return cmd_install_packs(cfg)
    if args.command == "soundcheck":
        return cmd_soundcheck(cfg)
    if args.command == "test":
        return cmd_test(cfg)
    if args.command == "toggle":
        return cmd_toggle()
    if args.command == "state":
        return cmd_state()
    if args.command == "status":
        return cmd_status()
    if args.command == "pack":
        return cmd_pack(cfg, args.id)
    if args.command == "next-pack":
        return cmd_next_pack(cfg)
    if args.command == "set":
        return cmd_set(cfg, args.pairs)
    if args.command == "run":
        if getattr(args, "volume", None) is not None:
            cfg.volume = args.volume
        if getattr(args, "pack", None):
            cfg.pack = args.pack
        if getattr(args, "device", None):
            cfg.audio_device = args.device
        return cmd_run(cfg, verbose=args.verbose)
    print("unknown command")
    return 1


if __name__ == "__main__":
    sys.exit(main())
