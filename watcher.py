#!/usr/bin/env python3
"""ADS-B callsign watcher — polls dump1090 and fires desktop notifications for watched callsigns."""

import json
import fnmatch
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse


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


def load_config() -> dict | None:
    path = config_path()
    if not path.exists():
        print(f"Config not found at {path}. Copy config.json there to get started.")
        sys.exit(1)
    try:
        with path.open() as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[{now()}] Config parse error: {e}")
        return None


def fetch_aircraft(url: str) -> list[dict] | None:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.load(resp)
            return data.get("aircraft", [])
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"[{now()}] Fetch error: {e}")
        return None


def matches_watchlist(callsign: str, watchlist: list[str]) -> str | None:
    """Return the matching pattern if callsign matches any watchlist entry, else None."""
    cs = callsign.strip().upper()
    for pattern in watchlist:
        if fnmatch.fnmatch(cs, pattern.upper()):
            return pattern
    return None


def _click_url(callsign: str, aircraft: dict, config: dict) -> str | None:
    action = config.get("click_action", "fr24")
    cs = callsign.strip()
    if action == "fr24":
        lat = aircraft.get("lat")
        lon = aircraft.get("lon")
        if lat is not None and lon is not None:
            return f"https://www.flightradar24.com/{lat:.4f},{lon:.4f}/11"
        return "https://www.flightradar24.com/"
    if action == "planefinder":
        return f"https://planefinder.net/flight/{cs}"
    if action == "opensky":
        hex_code = aircraft.get("hex", "").strip().lower()
        return f"https://opensky-network.org/aircraft-profile?icao24={hex_code}" if hex_code else None
    if action == "receiver":
        parsed = urlparse(config.get("receiver_url", ""))
        return f"{parsed.scheme}://{parsed.netloc}/"
    return None


def _send_notification(title: str, message: str, url: str | None = None):
    try:
        if sys.platform == "darwin":
            tn = shutil.which("terminal-notifier") or next(
                (p for p in [
                    "/opt/homebrew/bin/terminal-notifier",
                    "/usr/local/bin/terminal-notifier",
                ] if Path(p).exists()), None
            )
            if tn and url:
                subprocess.run([tn, "-title", title, "-message", message, "-open", url], check=False)
            else:
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


def notify_aircraft(callsign: str, aircraft: dict, pattern: str, config: dict):
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
        url=_click_url(callsign, aircraft, config),
    )
    print(f"[{now()}] SIGHTED  {callsign.strip():<10}  {detail_str}  (matched: {pattern})")


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _install_service_macos(args: list[str]):
    args_xml = "\n".join(f"        <string>{a}</string>" for a in args)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.adsb-watcher</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
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


def _install_service_linux(args: list[str]):
    service = f"""[Unit]
Description=ADS-B callsign watcher
After=network-online.target
Wants=network-online.target

[Service]
ExecStart={" ".join(args)}
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


def _install_service_windows(args: list[str]):
    command, *arguments = args
    args_xml = "".join(f"<Argument>{a}</Argument>" for a in arguments)
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
    <Exec><Command>{command}</Command>{args_xml}</Exec>
  </Actions>
</Task>"""
    tmp = Path(os.environ.get("TEMP", Path.home())) / "adsb-watcher-task.xml"
    tmp.write_text(xml, encoding="utf-16")
    subprocess.run(["schtasks", "/create", "/xml", str(tmp), "/tn", "ADS-B Watcher"], check=False)
    tmp.unlink(missing_ok=True)
    print("Task Scheduler entry created. It will start at next login.")
    print('To remove: schtasks /delete /tn "ADS-B Watcher"')


def _service_args() -> list[str]:
    script = Path(sys.argv[0]).resolve()
    if script.suffix == ".py":
        return [sys.executable, str(script)]
    return [str(script)]


def install_service():
    args = _service_args()
    if sys.platform == "darwin":
        _install_service_macos(args)
    elif sys.platform == "linux":
        _install_service_linux(args)
    elif sys.platform == "win32":
        _install_service_windows(args)
    else:
        print(f"Unsupported platform: {sys.platform}")
        sys.exit(1)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "install-service":
        install_service()
        return

    print(f"ADS-B Watcher starting. Config: {config_path()}")
    last_notified: dict[str, datetime] = {}
    receiver_down = False
    active_receiver_url = None

    while True:
        config = load_config()
        if config is None:
            time.sleep(5)
            continue

        url = config["receiver_url"]

        if url != active_receiver_url:
            if active_receiver_url is not None:
                print(f"[{now()}] Receiver changed, resetting cooldown timers.")
                last_notified.clear()
            active_receiver_url = url
        poll = config["poll_interval_seconds"]
        cooldown = timedelta(minutes=config["resight_cooldown_minutes"])
        watchlist = config["watchlist"]

        aircraft_list = fetch_aircraft(url)
        now_dt = datetime.now()

        if aircraft_list is None:
            if not receiver_down:
                _send_notification("ADS-B Watcher: receiver unreachable", url)
                receiver_down = True
            time.sleep(poll)
            continue

        receiver_down = False
        matched = 0

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
                notify_aircraft(raw_callsign, ac, pattern, config)
                last_notified[cs_key] = now_dt
            matched += 1

        print(f"[{now()}] {len(aircraft_list)} aircraft, {matched} matched")

        cutoff = now_dt - cooldown * 4
        last_notified = {k: v for k, v in last_notified.items() if v > cutoff}

        time.sleep(poll)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
