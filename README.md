# adsb-watcher

Polls a [dump1090](https://github.com/flightaware/dump1090) receiver and fires a desktop notification whenever a watched callsign appears overhead. Works on macOS, Linux, and Windows.

## Requirements

- Python 3.11+
- A running dump1090 instance on your network

## Setup

```
git clone https://github.com/aconaway1/adsb-watcher.git
cd adsb-watcher
```

Copy the example config and edit it:

**macOS / Linux**
```
mkdir -p ~/.config/adsb-watcher
cp config.example.json ~/.config/adsb-watcher/config.json
```

**Windows**
```
mkdir %APPDATA%\adsb-watcher
copy config.example.json %APPDATA%\adsb-watcher\config.json
```

Then open `config.json` and fill in your receiver address and watchlist.

| Field | Description |
|---|---|
| `receiver_url` | URL to your dump1090 `aircraft.json` endpoint |
| `poll_interval_seconds` | How often to query the receiver |
| `resight_cooldown_minutes` | Minimum time between repeat notifications for the same callsign |
| `click_action` | Where to go when you click a notification: `fr24`, `planefinder`, `opensky`, or `receiver` (defaults to `fr24`) |
| `watchlist` | List of callsigns or glob patterns to watch |

### Click actions

Clicking a notification opens a page for the matched flight. Requires [`terminal-notifier`](https://github.com/julienXX/terminal-notifier) on macOS (`brew install terminal-notifier`); without it, notifications fire but are not clickable. Click actions on Linux and Windows are not yet implemented.

Watchlist entries are case-insensitive and support `*` and `?` wildcards — `DL*` matches any Delta flight, `N????E` matches any 4-character N-number ending in E.

## Updating

```
git pull
```

Config changes take effect on the next poll cycle. If you've installed the background service, restart it to pick up code changes:

**macOS:** `launchctl unload ~/Library/LaunchAgents/com.adsb-watcher.plist && launchctl load ~/Library/LaunchAgents/com.adsb-watcher.plist`

**Linux:** `systemctl --user restart adsb-watcher`

**Windows:** `schtasks /end /tn "ADS-B Watcher" && schtasks /run /tn "ADS-B Watcher"`

## Running

```
python watcher.py
```

Logs sightings to stdout. Press Ctrl-C to stop.

## Running as a background service

```
python watcher.py install-service
```

This registers the watcher with the native service manager for your platform (launchd on macOS, systemd on Linux, Task Scheduler on Windows) and starts it immediately. The service restarts automatically on failure and runs at login.
