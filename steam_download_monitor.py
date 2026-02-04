import os
import re
import sys
import time
from pathlib import Path
import datetime

KV_RE = re.compile(r'"([^"]+)"\s*"([^"]*)"')


def get_steam_path() -> Path:
    import winreg

    keys = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
    ]

    for root, sub, name in keys:
        try:
            with winreg.OpenKey(root, sub) as k:
                value, _ = winreg.QueryValueEx(k, name)
                path = Path(value)
                if path.exists():
                    return path
        except OSError:
            pass

    raise RuntimeError("Steam not found")


def parse_kv(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {}
    return dict(KV_RE.findall(text))


def get_libraries(steam_root: Path) -> list[Path]:
    libs = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"

    if vdf.exists():
        for _, val in KV_RE.findall(vdf.read_text(encoding="utf-8", errors="ignore")):
            p = Path(val)
            if p.exists():
                libs.append(p)

    return list({p.resolve() for p in libs})


def find_active_download(libs: list[Path]):
    latest = None

    for lib in libs:
        droot = lib / "steamapps" / "downloading"
        if not droot.exists():
            continue

        for d in droot.iterdir():
            if d.is_dir() and d.name.isdigit():
                mtime = d.stat().st_mtime
                if not latest or mtime > latest[0]:
                    latest = (mtime, d.name, d)

    return latest[1:] if latest else (None, None)


def game_name(appid: str, libs: list[Path]) -> str:
    for lib in libs:
        mf = lib / "steamapps" / f"appmanifest_{appid}.acf"
        if mf.exists():
            return parse_kv(mf).get("name", f"AppID {appid}")
    return f"AppID {appid}"


def dir_size(path: Path) -> int:
    return sum(
        f.stat().st_size
        for r, _, files in os.walk(path)
        for f in map(lambda x: Path(r) / x, files)
        if f.exists()
    )


def status(speed: float) -> str:
    return "DOWNLOADING" if speed > 50_000 else "PAUSED"


def fmt(bps: float) -> str:
    return f"{bps / 1024 / 1024:.2f} MB/s"


def main():
    if sys.platform != "win32":
        print("Windows only")
        return

    steam = get_steam_path()
    libs = get_libraries(steam)

    last_size = last_time = None

    for _ in range(5):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        appid, path = find_active_download(libs)

        if not appid:
            print(f"[{now}] No active downloads")
            last_size = last_time = None
        else:
            size = dir_size(path)
            t = time.time()

            speed = 0.0
            if last_size is not None:
                speed = max(0, size - last_size) / max(1e-6, t - last_time)

            print(
                f"[{now}] {game_name(appid, libs)} | "
                f"{status(speed)} | {fmt(speed)}"
            )

            last_size, last_time = size, t

        time.sleep(60)


if __name__ == "__main__":
    main()