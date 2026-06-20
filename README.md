# adsb-watcher

Polls a [dump1090](https://github.com/flightaware/dump1090) receiver and fires a desktop notification whenever a watched callsign appears overhead. Works on macOS, Linux, and Windows.

## Requirements

- Python 3.11+
- [pipx](https://pipx.pypa.io/) (recommended) or pip
- A running dump1090 instance on your network

## Installation

**From the repository:**
```
pipx install git+https://github.com/aconaway1/adsb-watcher.git
```

**From a local clone:**
```
pipx install .
```

If `adsb-watcher` isn't found after installing, run `pipx ensurepath` and open a new terminal.

## Configuration

Copy the example config to the config directory and edit it:

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
| `watchlist` | List of callsigns or glob patterns to watch |

Watchlist entries are case-insensitive and support `*` and `?` wildcards — `DL*` matches any Delta flight, `N????E` matches any 4-character N-number ending in E.

## Running manually

```
adsb-watcher
```

Logs sightings to stdout. Press Ctrl-C to stop.

## Running as a background service

```
adsb-watcher install-service
```

This registers the watcher with the native service manager for your platform (launchd on macOS, systemd on Linux, Task Scheduler on Windows) and starts it immediately. The service restarts automatically on failure and runs at login.
