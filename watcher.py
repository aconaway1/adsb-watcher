#!/usr/bin/env python3
"""ADS-B callsign watcher — polls dump1090 and fires desktop notifications for watched callsigns."""

import json
import fnmatch
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path


def config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    candidate = base / "adsb-watcher" / "config.json"
    if not candidate.exists():
        local = Path(__file__).parent / "config.json"
        if local.exists():
            return local
    return candidate


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        print(f"Config not found at {path}. Copy config.json there to get started.")
        sys.exit(1)
    with path.open() as f:
        return json.load(f)


def fetch_aircraft(url: str) -> list[dict]:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.load(resp)
            return data.get("aircraft", [])
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"[{now()}] Fetch error: {e}")
        return []


def matches_watchlist(callsign: str, watchlist: list[str]) -> str | None:
    """Return the matching pattern if callsign matches any watchlist entry, else None."""
    cs = callsign.strip().upper()
    for pattern in watchlist:
        if fnmatch.fnmatch(cs, pattern.upper()):
            return pattern
    return None


def _send_notification(title: str, message: str):
    try:
        if sys.platform == "darwin":
            t = title.replace("\\", "\\\\").replace('"', '\\"')
            m = message.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(
                ["osascript", "-e", f'display notification "{m}" with title "{t}"'],
                check=False,
            )
        elif sys.platform == "linux":
            subprocess.run(["notify-send", title, message], check=False)
        elif sys.platform == "win32":
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "$n = New-Object System.Windows.Forms.NotifyIcon;"
                "$n.Icon = [System.Drawing.SystemIcons]::Information;"
                "$n.Visible = $true;"
                f"$n.ShowBalloonTip(10000, '{title}', '{message}', "
                "[System.Windows.Forms.ToolTipIcon]::None);"
                "Start-Sleep -Seconds 11"
            )
            subprocess.Popen(["powershell", "-Command", ps])
    except Exception as e:
        print(f"[{now()}] Notification error: {e}")


def notify_aircraft(callsign: str, aircraft: dict, pattern: str):
    details = []
    if "altitude" in aircraft:
        details.append(f"Alt {aircraft['altitude']:,} ft")
    if "speed" in aircraft:
        details.append(f"Spd {aircraft['speed']} kt")
    if "lat" in aircraft and "lon" in aircraft:
        details.append(f"{aircraft['lat']:.3f}, {aircraft['lon']:.3f}")

    detail_str = "  •  ".join(details) if details else "No position data"
    _send_notification(
        title=f"ADS-B: {callsign.strip()} sighted",
        message=f"{detail_str}  (matched: {pattern})",
    )
    print(f"[{now()}] SIGHTED  {callsign.strip():<10}  {detail_str}  (matched: {pattern})")


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def main():
    print(f"ADS-B Watcher starting. Config: {config_path()}")
    last_notified: dict[str, datetime] = {}

    while True:
        config = load_config()
        url = config["receiver_url"]
        poll = config["poll_interval_seconds"]
        cooldown = timedelta(minutes=config["resight_cooldown_minutes"])
        watchlist = config["watchlist"]

        aircraft_list = fetch_aircraft(url)
        now_dt = datetime.now()

        for ac in aircraft_list:
            raw_callsign = ac.get("flight", "")
            if not raw_callsign.strip():
                continue

            pattern = matches_watchlist(raw_callsign, watchlist)
            if not pattern:
                continue

            cs_key = raw_callsign.strip().upper()
            last = last_notified.get(cs_key)
            if last is None or (now_dt - last) >= cooldown:
                notify_aircraft(raw_callsign, ac, pattern)
                last_notified[cs_key] = now_dt

        cutoff = now_dt - cooldown * 4
        last_notified = {k: v for k, v in last_notified.items() if v > cutoff}

        time.sleep(poll)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
