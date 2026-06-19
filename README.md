# adsb-watcher

Polls a [dump1090](https://github.com/flightaware/dump1090) receiver and fires a desktop notification whenever a watched callsign appears overhead. Works on macOS, Linux, and Windows.

## Requirements

- Python 3.11+
- [pipx](https://pipx.pypa.io/) (recommended) or pip
- A running dump1090 instance on your network

## Installation

```
pipx install .
```

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

### macOS (launchd)

1. Edit `services/com.adsb-watcher.plist` and replace the path placeholder with the output of `which adsb-watcher`.

2. Install and start the LaunchAgent:
   ```
   cp services/com.adsb-watcher.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.adsb-watcher.plist
   ```

3. Logs are written to `/tmp/adsb-watcher.log`.

To stop: `launchctl unload ~/Library/LaunchAgents/com.adsb-watcher.plist`

### Linux (systemd)

```
cp services/adsb-watcher.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now adsb-watcher
```

The unit file assumes `adsb-watcher` is installed at `~/.local/bin/adsb-watcher` (the pipx default). Adjust `ExecStart` if your path differs.

View logs: `journalctl --user -u adsb-watcher -f`

To stop: `systemctl --user disable --now adsb-watcher`

### Windows (Task Scheduler)

1. Find the full path to the installed binary:
   ```
   where adsb-watcher
   ```

2. Edit `services\adsb-watcher.xml` and replace `adsb-watcher` in the `<Command>` element with that full path.

3. Import the task:
   ```
   schtasks /create /xml services\adsb-watcher.xml /tn "ADS-B Watcher"
   ```

The task runs at login and restarts automatically on failure.

To stop: `schtasks /delete /tn "ADS-B Watcher"`
