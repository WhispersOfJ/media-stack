#!/usr/bin/env python3
"""Populates DebridMediaManager's local IMDB title index (imdb_title_basics/
imdb_title_akas/imdb_title_ratings in dmm-mysql) from IMDB's public
non-commercial dataset dumps. Run daily by
systemd/stack-imdb-sync.{service,timer}.

Only these 3 tables are populated - src/services/database/imdbSearch.ts
(the actual search query, read directly from the pinned DMM commit) never
touches imdb_title_episode/imdb_name_basics/imdb_genres/etc, so importing
those would be wasted effort. Rows are filtered to exactly what the search
query itself filters on (title_type IN movie/tvSeries/tvMiniSeries,
is_adult = 0) - anything outside that filter would never surface in search
results anyway, so there's no reason to store it.

Streams each .tsv.gz directly from datasets.imdbws.com (no full file ever
written to disk unfiltered), filters in-flight, and pipes the filtered TSV
into the dmm-mysql container via `docker exec` stdin - not a direct host
bind-mount write, since MySQL's own entrypoint chowns
config/dmm-mysql-import to a container-internal uid on every start
(confirmed live), which blocks host-side writes to that path entirely.

Full TRUNCATE + LOAD DATA INFILE refresh each run, not incremental - IMDB's
dumps aren't diff-friendly, and a REPLACE-based upsert on 10M+ rows is
meaningfully slower than a clean reload.
"""
import gzip
import subprocess
import sys
import urllib.request
from pathlib import Path

STACK_DIR = Path(__file__).resolve().parent.parent
CONTAINER = "dmm-mysql"
IMPORT_DIR = "/var/lib/mysql-files/import"
KEPT_TITLE_TYPES = {"movie", "tvSeries", "tvMiniSeries"}
DISCORD_BLURPLE = 0x5865F2
DISCORD_RED = 0xED4245


def env_get(key):
    env_path = STACK_DIR / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


DISCORD_WEBHOOK_URL = env_get("DISCORD_WEBHOOK_URL")
MYSQL_ROOT_PASSWORD = env_get("DMM_MYSQL_ROOT_PASSWORD")


def post_discord(title, description, color):
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "changeme":
        print("DISCORD_WEBHOOK_URL not configured, skipping notification", file=sys.stderr)
        return
    body = {"embeds": [{"title": title, "description": description, "color": color}]}
    import json

    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15):
            pass
    except Exception as e:
        print(f"Discord notification failed: {e}", file=sys.stderr)


def stream_gz_rows(url):
    """Yields tab-split rows from a remote .tsv.gz, decompressing while downloading."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        with gzip.GzipFile(fileobj=resp) as gz:
            header = gz.readline()  # discard column header row
            for line in gz:
                yield line.decode("utf-8", errors="replace").rstrip("\n").split("\t")


def load_into_table(table, columns, line_iter):
    """Pipes filtered TSV lines into the container, then TRUNCATE + LOAD DATA INFILE."""
    filename = f"{table}.tsv"
    container_path = f"{IMPORT_DIR}/{filename}"

    write_proc = subprocess.Popen(
        ["docker", "exec", "-i", CONTAINER, "sh", "-c", f"cat > {container_path}"],
        stdin=subprocess.PIPE,
    )
    row_count = 0
    for line in line_iter:
        write_proc.stdin.write((line + "\n").encode("utf-8", errors="replace"))
        row_count += 1
    write_proc.stdin.close()
    write_proc.wait()
    if write_proc.returncode != 0:
        raise RuntimeError(f"Failed writing {filename} into {CONTAINER}")

    col_list = ", ".join(columns)
    sql = f"TRUNCATE {table}; LOAD DATA INFILE '{container_path}' INTO TABLE {table} FIELDS TERMINATED BY '\\t' ({col_list});"
    result = subprocess.run(
        [
            "docker",
            "exec",
            CONTAINER,
            "mysql",
            "-u",
            "root",
            f"-p{MYSQL_ROOT_PASSWORD}",
            "dmm",
            "-e",
            sql,
        ],
        capture_output=True,
        text=True,
    )
    subprocess.run(["docker", "exec", CONTAINER, "rm", "-f", container_path])
    if result.returncode != 0:
        raise RuntimeError(f"LOAD DATA INFILE failed for {table}: {result.stderr}")
    return row_count


def get_row_count(table):
    result = subprocess.run(
        [
            "docker",
            "exec",
            CONTAINER,
            "mysql",
            "-u",
            "root",
            f"-p{MYSQL_ROOT_PASSWORD}",
            "dmm",
            "-N",
            "-e",
            f"SELECT COUNT(*) FROM {table};",
        ],
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip()) if result.returncode == 0 else -1


def main():
    if not MYSQL_ROOT_PASSWORD or MYSQL_ROOT_PASSWORD == "changeme":
        print("DMM_MYSQL_ROOT_PASSWORD not configured", file=sys.stderr)
        sys.exit(1)

    # --- title.basics: filter first, defines the kept tconst set everything else filters against ---
    kept_tconsts = set()

    def basics_rows():
        for cols in stream_gz_rows("https://datasets.imdbws.com/title.basics.tsv.gz"):
            if len(cols) < 9:
                continue
            tconst, title_type, primary_title, original_title, is_adult, start_year, end_year, runtime_minutes, _genres = cols
            if title_type not in KEPT_TITLE_TYPES or is_adult == "1":
                continue
            kept_tconsts.add(tconst)
            yield "\t".join(
                [tconst, title_type, primary_title, original_title, is_adult, start_year, end_year, runtime_minutes]
            )

    basics_n = load_into_table(
        "imdb_title_basics",
        ["tconst", "title_type", "primary_title", "original_title", "is_adult", "start_year", "end_year", "runtime_minutes"],
        basics_rows(),
    )

    # --- title.ratings: filtered to the kept tconst set ---
    def ratings_rows():
        for cols in stream_gz_rows("https://datasets.imdbws.com/title.ratings.tsv.gz"):
            if len(cols) < 3:
                continue
            tconst = cols[0]
            if tconst not in kept_tconsts:
                continue
            yield "\t".join(cols[:3])

    ratings_n = load_into_table("imdb_title_ratings", ["tconst", "average_rating", "num_votes"], ratings_rows())

    # --- title.akas: filtered to the kept tconst set ---
    def akas_rows():
        for cols in stream_gz_rows("https://datasets.imdbws.com/title.akas.tsv.gz"):
            if len(cols) < 8:
                continue
            title_id = cols[0]
            if title_id not in kept_tconsts:
                continue
            yield "\t".join(cols[:8])

    akas_n = load_into_table(
        "imdb_title_akas",
        ["title_id", "ordering", "title", "region", "language", "types", "attributes", "is_original_title"],
        akas_rows(),
    )

    final_counts = {t: get_row_count(t) for t in ("imdb_title_basics", "imdb_title_ratings", "imdb_title_akas")}
    print(f"Imported: basics={basics_n} ratings={ratings_n} akas={akas_n} | final row counts: {final_counts}")

    post_discord(
        "DMM IMDB sync completed",
        f"basics: {final_counts['imdb_title_basics']:,}\n"
        f"ratings: {final_counts['imdb_title_ratings']:,}\n"
        f"akas: {final_counts['imdb_title_akas']:,}",
        DISCORD_BLURPLE,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"IMDB sync failed: {e}", file=sys.stderr)
        post_discord("DMM IMDB sync failed", str(e), DISCORD_RED)
        sys.exit(1)
