"""Makes a consistent copy of the database (and optionally uploaded files).

    python manage.py backup_data                 # database only
    python manage.py backup_data --include-files # also the uploaded images and PDFs
    python manage.py backup_data --list

Each backup is a folder in BACKUP_DIR (default: backend\\backups) with a manifest.json that records
what it holds and a SHA-256 checksum of every file. Only the newest BACKUP_KEEP backups are kept,
because backups contain personal data and retention applies to them too.

Restoring is described in docs/DEPLOYMENT.md. It is deliberately not automatic.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class Command(BaseCommand):
    help = "Back up the database (and optionally uploaded files) to BACKUP_DIR."

    def add_arguments(self, parser):
        parser.add_argument("--include-files", action="store_true",
                            help="Also copy uploaded files. They include identity documents; see docs/SECURITY.md.")
        parser.add_argument("--list", action="store_true", help="List existing backups and stop.")

    def handle(self, *args, **opts):
        root = Path(settings.BACKUP_DIR)
        if opts["list"]:
            for manifest in sorted(root.glob("*/manifest.json")):
                data = json.loads(manifest.read_text(encoding="utf-8"))
                self.stdout.write(f"{manifest.parent.name}  {data['database']['engine']}  {len(data['files'])} file(s)")
            return

        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        target = root / f"backup-{stamp}"
        target.mkdir(parents=True, exist_ok=False)
        try:
            files = [self._database(target)]
            if opts["include_files"] and Path(settings.MEDIA_ROOT).exists():
                shutil.make_archive(str(target / "media"), "zip", settings.MEDIA_ROOT)
                files.append(target / "media.zip")
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
        manifest = {
            "created_at": timezone.now().isoformat(), "app_version": settings.APP_VERSION,
            "database": {"engine": connection.vendor},
            "files": [{"name": f.name, "bytes": f.stat().st_size, "sha256": _sha256(f)} for f in files],
            "contains_personal_data": True,
        }
        (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        removed = self._prune(root)
        self.stdout.write(self.style.SUCCESS(f"Backup saved to {target}"))
        if removed:
            self.stdout.write(f"Removed {removed} older backup(s); keeping the newest {settings.BACKUP_KEEP}.")

    def _database(self, target: Path) -> Path:
        db = settings.DATABASES["default"]
        if connection.vendor == "sqlite":
            # SQLite's own backup copies a consistent snapshot even while the server is running.
            out = target / "db.sqlite3"
            source = sqlite3.connect(str(db["NAME"]))
            dest = sqlite3.connect(str(out))
            with dest:
                source.backup(dest)
            dest.close()
            source.close()
            return out
        if connection.vendor == "postgresql":
            if shutil.which("pg_dump") is None:
                raise CommandError("pg_dump wasn't found. Add PostgreSQL's bin folder to PATH and try again.")
            out = target / "db.dump"
            env = {"PGPASSWORD": str(db.get("PASSWORD", ""))}
            command = ["pg_dump", "-Fc", "-f", str(out), "-h", str(db.get("HOST") or "localhost"),
                       "-p", str(db.get("PORT") or 5432), "-U", str(db.get("USER", "")), str(db["NAME"])]
            subprocess.run(command, check=True, env={**os.environ, **env})
            return out
        raise CommandError(f"Backups aren't supported for {connection.vendor}.")

    def _prune(self, root: Path) -> int:
        backups = sorted(p.parent for p in root.glob("backup-*/manifest.json"))
        old = backups[:-settings.BACKUP_KEEP] if settings.BACKUP_KEEP > 0 else []
        for folder in old:
            shutil.rmtree(folder, ignore_errors=True)
        return len(old)
