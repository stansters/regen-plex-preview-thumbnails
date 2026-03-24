#!/usr/bin/env python3
import sys
import argparse
import subprocess
import requests

PLEX_URL = "http://localhost:32400"
PLEX_TOKEN = "YOUR_TOKEN_HERE"
DB = "/var/snap/plexmediaserver/common/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db"
BIF_BASE = "/var/snap/plexmediaserver/common/Library/Application Support/Plex Media Server/Media/localhost"
SQLITE = "/snap/plexmediaserver/512/Plex SQLite"

def plex_get(path, params={}):
    params["X-Plex-Token"] = PLEX_TOKEN
    r = requests.get(f"{PLEX_URL}{path}", params=params, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()["MediaContainer"]

def search_show(name):
    results = plex_get("/search", {"query": name}).get("Metadata", [])
    shows = [x for x in results if x.get("type") == "show"]
    if not shows:
        print(f"No shows found for: {name}")
        sys.exit(1)
    if len(shows) > 1:
        print("Multiple shows found, using first match:")
        for s in shows:
            print(f"  {s['title']} (ID: {s['ratingKey']})")
    show = shows[0]
    print(f"Found: {show['title']} (ID: {show['ratingKey']})")
    return show

def get_seasons(show_id, season_filter=None):
    seasons = plex_get(f"/library/metadata/{show_id}/children").get("Metadata", [])
    if season_filter:
        seasons = [s for s in seasons if s.get("index") in season_filter]
    return seasons

def sqlite_query(query):
    result = subprocess.run(
        ["sudo", SQLITE, DB, query],
        capture_output=True, text=True
    )
    return result.stdout.strip().splitlines()

def resolve_bif(hash_val):
    h = hash_val.lstrip("!")
    return f"{BIF_BASE}/{h[0]}/{h[1:]}.bundle/Contents/Indexes/index-sd.bif"

def delete_bif(bif):
    result = subprocess.run(["sudo", "test", "-f", bif])
    if result.returncode == 0:
        subprocess.run(["sudo", "rm", "-f", bif])
        print(f"  Deleted: {bif}")
    else:
        print(f"  Not found (skipping): {bif}")

def analyze(episode_id):
    requests.put(
        f"{PLEX_URL}/library/metadata/{episode_id}/analyze",
        params={"X-Plex-Token": PLEX_TOKEN}
    )

def main():
    parser = argparse.ArgumentParser(description="Regenerate Plex video preview thumbnails for a show")
    parser.add_argument("show", nargs="+", help="Show name")
    parser.add_argument("--season", help="Comma-separated season numbers (e.g. 1,2,3). Omit for all seasons.")
    parser.add_argument("--episode", help="Comma-separated episode numbers (e.g. 1,2,3). Requires --season.")
    args = parser.parse_args()

    if args.episode and not args.season:
        print("--episode requires --season to be specified.")
        sys.exit(1)

    show_name = " ".join(args.show)
    season_filter = [int(s) for s in args.season.split(",")] if args.season else None
    episode_filter = [int(e) for e in args.episode.split(",")] if args.episode else None

    show = search_show(show_name)
    seasons = get_seasons(show["ratingKey"], season_filter)

    if not seasons:
        print("No matching seasons found.")
        sys.exit(1)

    all_episode_ids = []
    for season in seasons:
        print(f"\nSeason {season.get('index', '?')}: {season['title']} (ID: {season['ratingKey']})")
        episodes = plex_get(f"/library/metadata/{season['ratingKey']}/children").get("Metadata", [])
        if episode_filter:
            episodes = [e for e in episodes if e.get("index") in episode_filter]
        for e in episodes:
            print(f"  E{e.get('index', '?')}: {e['title']} (ID: {e['ratingKey']})")
        all_episode_ids.extend([e["ratingKey"] for e in episodes])

    if not all_episode_ids:
        print("No episodes found.")
        sys.exit(1)

    id_list = ",".join(all_episode_ids)
    print(f"\nLooking up BIF files for {len(all_episode_ids)} episodes...")
    rows = sqlite_query(
        f"SELECT hash FROM media_parts WHERE media_item_id IN "
        f"(SELECT id FROM media_items WHERE metadata_item_id IN ({id_list}))"
    )

    bif_paths = [resolve_bif(row.split("|")[-1]) for row in rows]

    print(f"\nBIF files to delete:")
    found = []
    for bif in bif_paths:
        result = subprocess.run(["sudo", "test", "-f", bif])
        if result.returncode == 0:
            print(f"  [EXISTS] {bif}")
            found.append(bif)
        else:
            print(f"  [MISSING] {bif}")

    print(f"\n{len(found)}/{len(bif_paths)} BIF files found.")
    confirm = input(f"Delete and requeue analysis for {len(all_episode_ids)} episodes? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        sys.exit(0)

    print(f"\nDeleting BIF files...")
    for bif in found:
        delete_bif(bif)

    print(f"\nQueuing reanalysis...")
    for ep_id in all_episode_ids:
        analyze(ep_id)
        print(f"  Queued: {ep_id}")

    print("\nDone. Plex will regenerate thumbnails during the next analysis pass.")

if __name__ == "__main__":
    main()