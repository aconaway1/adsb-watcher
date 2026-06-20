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


def _install_service_macos(binary: str):
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.adsb-watcher</string>
    <key>ProgramArguments</key>
    <array>
        <string>{binary}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/adsb-watcher.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/adsb-watcher.log</string>
</dict>
</plist>"""
    dest = Path.home() / "Library" / "LaunchAgents" / "com.adsb-watcher.plist"
    dest.write_text(plist)
    subprocess.run(["launchctl", "load", str(dest)], check=False)
    print(f"Installed and started. Logs: /tmp/adsb-watcher.log")
    print(f"To stop: launchctl unload {dest}")


def _install_service_linux(binary: str):
    service = f"""[Unit]
Description=ADS-B callsign watcher
After=network-online.target
Wants=network-online.target

[Service]
ExecStart={binary}
Restart=on-failure
RestartSec=15

[Install]
WantedBy=default.target
"""
    dest_dir = Path.home() / ".config" / "systemd" / "user"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "adsb-watcher.service"
    dest.write_text(service)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", "--now", "adsb-watcher"], check=False)
    print("Installed and started.")
    print("Logs: journalctl --user -u adsb-watcher -f")
    print(f"To stop: systemctl --user disable --now adsb-watcher")


def _install_service_windows(binary: str):
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
  </Settings>
  <Actions>
    <Exec><Command>{binary}</Command></Exec>
  </Actions>
</Task>"""
    tmp = Path(os.environ.get("TEMP", Path.home())) / "adsb-watcher-task.xml"
    tmp.write_text(xml, encoding="utf-16")
    subprocess.run(["schtasks", "/create", "/xml", str(tmp), "/tn", "ADS-B Watcher"], check=False)
    tmp.unlink(missing_ok=True)
    print("Task Scheduler entry created. It will start at next login.")
    print('To remove: schtasks /delete /tn "ADS-B Watcher"')


def install_service():
    binary = str(Path(sys.argv[0]).resolve())
    if sys.platform == "darwin":
        _install_service_macos(binary)
    elif sys.platform == "linux":
        _install_service_linux(binary)
    elif sys.platform == "win32":
        _install_service_windows(binary)
    else:
        print(f"Unsupported platform: {sys.platform}")
        sys.exit(1)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "install-service":
        install_service()
        return

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
