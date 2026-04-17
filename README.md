# regen-plex-preview-thumbnails

Deletes and regenerates corrupted or missing video preview thumbnail BIF files for specific shows (optionally by season/episode) or movies in Plex — without having to reanalyze your entire library.

## Requirements

- Python 3
- `requests` library (`pip install requests`)
- Must be run on the Plex server itself

## Setup

Edit the constants at the top of `vpt-regen.py`:

```python
PLEX_URL = "http://localhost:32400"
PLEX_TOKEN = "your_token_here"
DB = "..."
BIF_BASE = "..."
SQLITE = "..."
```

**`PLEX_URL`** — URL to your Plex server. Since the script has to be run on the server itself, `localhost:32400` is fine in most cases.

**`PLEX_TOKEN`** — Your Plex authentication token. To find it: in Plex Web, open any item → ⋯ → Get Info → View XML. The token is in the URL as `X-Plex-Token=`.

**`DB`** — Path to Plex's SQLite database file (`com.plexapp.plugins.library.db`). To find it:
```bash
sudo find / -name "com.plexapp.plugins.library.db" 2>/dev/null
```
Common locations:
- Snap: `/var/snap/plexmediaserver/common/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db`
- Linux package: `/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db`

**`BIF_BASE`** — Directory where Plex stores BIF (thumbnail) files. Same base path as the DB, but ending in `Media/localhost`. To find it:
```bash
sudo find / -name "*.bif" 2>/dev/null | head -1
```
Strip everything from `/Media/localhost/` onward and use that as your base path.

**`SQLITE`** — Path to Plex's bundled SQLite binary. Using Plex's own binary ensures compatibility with its database. To find it:
```bash
sudo find / -name "Plex SQLite" 2>/dev/null
```
Common locations:
- Snap: `/snap/plexmediaserver/current/Plex SQLite`
- Linux package: `/usr/lib/plexmediaserver/Plex SQLite`

## Usage

```bash
# Show mode (default): regenerate all seasons/episodes of a show
python3 vpt-regen.py <show name>

# Show mode: specific seasons
python3 vpt-regen.py <show name> --season 1,2

# Show mode: specific episodes in a season
python3 vpt-regen.py <show name> --season 1 --episode 3,4,5

# Movie mode
python3 vpt-regen.py <movie name> --movie
```

### Examples

```bash
python3 vpt-regen.py fargo
python3 vpt-regen.py fargo --season 2
python3 vpt-regen.py breaking bad --season 3 --episode 1,2
python3 vpt-regen.py interstellar --movie
```

## What it does

1. Searches your Plex library for the show or movie
2. Lists matching seasons/episodes and their BIF file paths
3. Shows which BIF files exist and which are missing
4. Asks for confirmation before doing anything
5. Deletes the BIF files and queues reanalysis via the Plex API
6. Plex regenerates the thumbnails during the next analysis pass
