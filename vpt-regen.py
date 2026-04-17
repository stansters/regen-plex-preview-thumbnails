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

def search_movie(name):
    results = plex_get("/search", {"query": name}).get("Metadata", [])
    movies = [x for x in results if x.get("type") == "movie"]
    if not movies:
        print(f"No movies found for: {name}")
        sys.exit(1)
    if len(movies) > 1:
        print("Multiple movies found, using first match:")
        for m in movies:
            print(f"  {m['title']} (ID: {m['ratingKey']})")
    movie = movies[0]
    print(f"Found: {movie['title']} (ID: {movie['ratingKey']})")
    return movie

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

def analyze(metadata_id):
    requests.put(
        f"{PLEX_URL}/library/metadata/{metadata_id}/analyze",
        params={"X-Plex-Token": PLEX_TOKEN}
    )

def main():
    parser = argparse.ArgumentParser(description="Regenerate Plex video preview thumbnails for a show or movie")
    parser.add_argument("title", nargs="+", help="Show or movie title")
    parser.add_argument("--movie", action="store_true", help="Treat the title as a movie (default is show mode).")
    parser.add_argument("--season", help="Comma-separated season numbers (e.g. 1,2,3). Omit for all seasons.")
    parser.add_argument("--episode", help="Comma-separated episode numbers (e.g. 1,2,3). Requires --season.")
    args = parser.parse_args()

    if args.movie and (args.season or args.episode):
        print("--season and --episode cannot be used with --movie.")
        sys.exit(1)

    if not args.movie and args.episode and not args.season:
        print("--episode requires --season to be specified.")
        sys.exit(1)

    title_name = " ".join(args.title)
    season_filter = [int(s) for s in args.season.split(",")] if args.season else None
    episode_filter = [int(e) for e in args.episode.split(",")] if args.episode else None

    metadata_ids = []
    analyze_target_label = "items"

    if args.movie:
        movie = search_movie(title_name)
        metadata_ids = [movie["ratingKey"]]
        analyze_target_label = "movies"
    else:
        show = search_show(title_name)
        seasons = get_seasons(show["ratingKey"], season_filter)

        if not seasons:
            print("No matching seasons found.")
            sys.exit(1)

        for season in seasons:
            print(f"\nSeason {season.get('index', '?')}: {season['title']} (ID: {season['ratingKey']})")
            episodes = plex_get(f"/library/metadata/{season['ratingKey']}/children").get("Metadata", [])
            if episode_filter:
                episodes = [e for e in episodes if e.get("index") in episode_filter]
            for e in episodes:
                print(f"  E{e.get('index', '?')}: {e['title']} (ID: {e['ratingKey']})")
            metadata_ids.extend([e["ratingKey"] for e in episodes])
        analyze_target_label = "episodes"

    if not metadata_ids:
        print("No matching media found.")
        sys.exit(1)

    id_list = ",".join(str(metadata_id) for metadata_id in metadata_ids)
    print(f"\nLooking up BIF files for {len(metadata_ids)} {analyze_target_label}...")
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
    confirm = input(f"Delete and requeue analysis for {len(metadata_ids)} {analyze_target_label}? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        sys.exit(0)

    print(f"\nDeleting BIF files...")
    for bif in found:
        delete_bif(bif)

    print(f"\nQueuing reanalysis...")
    for metadata_id in metadata_ids:
        analyze(metadata_id)
        print(f"  Queued: {metadata_id}")

    print("\nDone. Plex will regenerate thumbnails during the next analysis pass.")

if __name__ == "__main__":
    main()
