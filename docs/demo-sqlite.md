# Persistent SQLite for the demo (#239)

Run all commands from the repository root with the project's virtual environment
active. Use a separate host-local directory that survives backend restarts; do
not use a network filesystem, Firebase's `public/` directory, or a real user's
database. For example, on Linux:

```bash
mkdir -p "$HOME/marketplace-demo/data" "$HOME/marketplace-demo/backups"
export DATABASE_URL="sqlite:///$HOME/marketplace-demo/data/marketplace.db"
export DEBUG=false
python -m src.database
python -m src.seed --demo
python -m src.main
```

Keep the same `DATABASE_URL` in every process and after every restart. The first
initialization creates the database and demo seed; initialization and migration
are repeatable and preserve records. Never run reset commands against an existing
database. Check `/health` for `database: connected`; this tests connectivity,
not the correctness of application data. A tunnel restart does not alter SQLite.

For a consistent online backup, use Python's SQLite backup API, with the source
and a **new** destination file on the host. Choose a unique filename each time:

```bash
python - "$HOME/marketplace-demo/data/marketplace.db" "$HOME/marketplace-demo/backups/backup-001.db" <<'PY'
import sqlite3, sys
from pathlib import Path
source, target = map(Path, sys.argv[1:])
if not source.is_file() or target.exists():
    raise SystemExit('Source must exist and backup destination must be new')
with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
    src.backup(dst)
PY
```

Restore to a **new test location** by using the same command with the backup as
source and a new restore filename as destination; run a separate backend with
`DATABASE_URL` pointing at that restore and verify a known record. Stop that
backend afterwards. To restore the active demo, stop the backend first, preserve
the current database and its SQLite sidecars, then use a verified backup at a
new path and change `DATABASE_URL`. Never overwrite a live database. Back up the
upload directory `src/web/static/uploads/products/` separately; the database
contains image URLs, not the files. Coordinate snapshots while writes are stopped
if an exact database-and-image pair is required. Protect backups as private data.

Acceptance evidence: write an authorized record, read it after backend restart,
read it after tunnel restart, rerun initialization and read it again, then read
it from an independently restored copy. Record actual results; the health check
alone does not establish persistence.
