# Running DocumentLab for real use (Windows)

Development (`runserver` + `npm run dev`) is for building DocumentLab. For real use, one production
server (Waitress) serves both the website and the API on one port, with debug mode off and every
security setting on. This guide sets that up on one Windows PC, then makes it reachable from other
computers over HTTPS.

All commands are PowerShell. Paths assume the project is in `C:\Projects\documentlab`.

---

## 1. Install the production packages

```powershell
cd C:\Projects\documentlab\backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

This adds **WhiteNoise** (serves the built website) and **Waitress** (the production web server).
For PostgreSQL also run `pip install -r requirements-postgres.txt` (step 8).

## 2. Build the website

```powershell
cd C:\Projects\documentlab\frontend
npm run build
```

This creates `frontend\dist`. Rebuild it after every update.

## 3. Create a secret key

Django signs sessions with a secret key. Production refuses to start without a long random one.

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Copy the output. Never share it, never commit it to Git, and use a different one for every installation.

## 4. Fill in `backend\.env`

Copy `backend\.env.example` to `backend\.env` if you haven't already, then set:

```ini
DJANGO_SECRET_KEY=<the key from step 3>
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000

# Only while trying production mode on this PC without HTTPS. Remove it before other people use DocumentLab.
DJANGO_ALLOW_HTTP=true

# Optional: where backups go, and how many to keep (they hold personal data, so don't keep more than you need).
# BACKUP_DIR=D:\DocumentLabBackups
# BACKUP_KEEP=14
```

`.env` is in `.gitignore`. Check with `git status` that it never appears there.

## 5. Prepare the database and check the configuration

```powershell
cd C:\Projects\documentlab\backend
$env:DJANGO_SETTINGS_MODULE = "config.settings.prod"
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

`check --deploy` lists every setting that isn't safe yet. While `DJANGO_ALLOW_HTTP=true` is set it will
warn about HTTPS, cookies and HSTS. That is expected on one PC, and is fixed by step 7.

If this is a new database, create the first administrator: `python manage.py createsuperuser`.

## 6. Start DocumentLab

```powershell
powershell -ExecutionPolicy Bypass -File C:\Projects\documentlab\scripts\start-production.ps1
```

The script applies any database updates, collects static files and starts Waitress. Open
**http://localhost:8000**. Stop it with `Ctrl + C`.

Sign in as an administrator and open **Settings**. The *Security and readiness* panel checks the running
configuration and says what is still missing (it measures the real settings; nothing is assumed).

To start DocumentLab automatically when the PC starts: Task Scheduler → *Create Task* → trigger
*At startup* → action *Start a program*: `powershell.exe` with arguments
`-ExecutionPolicy Bypass -File C:\Projects\documentlab\scripts\start-production.ps1`, and tick
*Run whether user is logged on or not*.

## 7. Let other computers connect, over HTTPS

Passwords and identity documents travel between the browser and the server, so on a network
DocumentLab must use HTTPS. The simplest way on Windows is **Caddy**, a small web server that handles
the certificate and passes requests to DocumentLab:

1. Download Caddy for Windows from https://caddyserver.com/download and put `caddy.exe` in `C:\Caddy`.
2. Create `C:\Caddy\Caddyfile` (replace the name with this PC's network name):

   ```
   documentlab.yourschool.local {
       tls internal
       reverse_proxy 127.0.0.1:8000
   }
   ```

   `tls internal` makes Caddy its own certificate authority, which suits a local network. Each computer
   that connects must trust Caddy's root certificate once (`caddy trust` prints where it is). If you have a
   real domain name that points at this server, remove `tls internal` and Caddy gets a public certificate
   automatically.
3. In `backend\.env`, **remove** `DJANGO_ALLOW_HTTP=true` and set:

   ```ini
   DJANGO_BEHIND_HTTPS_PROXY=true
   DJANGO_ALLOWED_HOSTS=documentlab.yourschool.local
   DJANGO_CSRF_TRUSTED_ORIGINS=https://documentlab.yourschool.local
   ```

4. Keep DocumentLab listening on `127.0.0.1` only (the default), so it can only be reached through Caddy.
   Start Caddy with `C:\Caddy\caddy.exe run --config C:\Caddy\Caddyfile`, and allow port 443 in Windows
   Defender Firewall.
5. Run `python manage.py check --deploy` again. With HTTPS on, the HTTPS warnings disappear.

> These Caddy steps follow Caddy's documented setup but have not been run on your network. Test from a
> second computer before relying on it.

## 8. Several users: PostgreSQL

SQLite (the default) is a single file and suits one person on one PC. For several people at once, use
PostgreSQL:

1. Install PostgreSQL for Windows from https://www.postgresql.org/download/windows/ and remember the
   password you choose for the `postgres` user.
2. Create a database and a user for DocumentLab (in *SQL Shell (psql)*):

   ```sql
   CREATE USER documentlab WITH PASSWORD 'choose-a-strong-password';
   CREATE DATABASE documentlab OWNER documentlab;
   ```

3. Install the driver and point DocumentLab at it:

   ```powershell
   pip install -r requirements-postgres.txt
   ```

   ```ini
   DATABASE_URL=postgres://documentlab:choose-a-strong-password@localhost:5432/documentlab
   ```

4. Run `python manage.py migrate`, then `createsuperuser`.

To move existing data from SQLite, back it up first (step 10), then with the old `DATABASE_URL`:
`python manage.py dumpdata --natural-foreign --exclude contenttypes --exclude auth.permission -o data.json`,
switch `DATABASE_URL`, run `migrate`, then `python manage.py loaddata data.json`. Copy the `media` folder
across too. `data.json` contains personal data, so delete it when you're done.

## 9. Daily maintenance (expired data and backups)

`scripts\daily-maintenance.ps1` deletes identity data whose retention period has ended, then makes a
backup of the database and uploaded files. Its output goes to `backend\logs\maintenance.log`.

Schedule it in Task Scheduler: *Create Task* → trigger *Daily* (for example 02:00) → action
*Start a program*: `powershell.exe` with arguments
`-ExecutionPolicy Bypass -File C:\Projects\documentlab\scripts\daily-maintenance.ps1`.

Run it once by hand first and read the log. The **Backups** item on the Settings page turns green once a
recent backup exists.

## 10. Backups and restoring

Each backup is a folder in `BACKUP_DIR` (default `backend\backups`) holding the database, optionally the
uploaded files, and `manifest.json` with a SHA-256 checksum of every file. Only the newest `BACKUP_KEEP`
backups are kept.

```powershell
python manage.py backup_data --include-files   # make one now
python manage.py backup_data --list            # see what exists
```

**Backups contain personal data.** Keep them on an encrypted drive (BitLocker) and copy them off the PC
regularly. A backup on the same disk doesn't survive that disk failing.

Restoring is deliberately manual, so it can't happen by accident:

**SQLite**
1. Stop DocumentLab.
2. Rename the current `backend\db.sqlite3` to `db.sqlite3.before-restore` (don't delete it yet).
3. Copy `db.sqlite3` from the backup folder to `backend\db.sqlite3`.
4. If the backup includes files, copy its `media` folder over `backend\media`.
5. Check the copy: `Get-FileHash backend\db.sqlite3 -Algorithm SHA256` must match the value in `manifest.json`.
6. Start DocumentLab, sign in and check the data. Then delete `db.sqlite3.before-restore`.

**PostgreSQL**
1. Stop DocumentLab.
2. `pg_restore --clean --if-exists -h localhost -U documentlab -d documentlab "<backup folder>\db.dump"`
3. Copy the backup's `media` folder over `backend\media`, start DocumentLab and check.

Restore into a test copy once, before you ever need it for real.

## 11. Updating to a new version

1. Run `daily-maintenance.ps1` (or `backup_data --include-files`) so there is a fresh backup.
2. Stop DocumentLab (`Ctrl + C`, or end the scheduled task). **Stop it before extracting files.**
3. Extract the new version over `C:\Projects`.
4. `pip install -r requirements.txt`, then `npm run build` in `frontend`.
5. `python manage.py run_test_lab` with `DJANGO_SETTINGS_MODULE=config.settings.prod`. Everything should pass.
6. Start DocumentLab with `start-production.ps1`. It applies database updates automatically.

## 12. Before other people use it

- [ ] Settings → *Security and readiness* shows no **Fail**.
- [ ] `python manage.py check --deploy` shows no HTTPS warnings (HTTPS through step 7).
- [ ] `DJANGO_ALLOW_HTTP` is not in `.env`.
- [ ] Every person has their own account with the least role they need. Nobody shares the administrator account.
- [ ] The daily maintenance task has run and produced a backup.
- [ ] The PC's disk is encrypted (BitLocker), because uploaded documents and backups are stored on it.
- [ ] You've read `docs/SECURITY.md` and `docs/LIMITATIONS.md`.
