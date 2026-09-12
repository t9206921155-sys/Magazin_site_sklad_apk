"""Блок 29: staging-автоматизация и гигиена — офлайн-тесты.

backup-drill прогоняется целиком на синтетической БД (без сервера).
staging-report — только --help/--dry-run/валидация (полный прогон
требует живого URL и выполняется владельцем на staging).
"""
import os
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = str(ROOT / "deploy" / "staging-report.sh")
DRILL = str(ROOT / "deploy" / "backup-drill.sh")
MOBILE_BUILD = str(ROOT / "mobile" / "build-apk.sh")
INSTALL = str(ROOT / "install.sh")


def run(cmd, env=None, **kw):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(cmd, capture_output=True, text=True, env=e, **kw)


# ---------- staging-report.sh ----------
def test_staging_help_and_dry_run():
    r = run(["bash", STAGING, "--help"])
    assert r.returncode == 0 and "DEVELOPER-MANUAL-VALIDATION" in r.stdout
    r = run(["bash", STAGING, "--dry-run"])
    assert r.returncode == 0 and "DRY-RUN" in r.stdout


def test_staging_requires_url():
    assert run(["bash", STAGING]).returncode != 0
    assert run(["bash", STAGING, "--nope"]).returncode != 0


# ---------- backup-drill.sh ----------
def test_drill_help_and_dry_run():
    r = run(["bash", DRILL, "--help"])
    assert r.returncode == 0 and "verify_restore" in r.stdout
    r = run(["bash", DRILL, "--dry-run"])
    assert r.returncode == 0 and "MANIFEST" in r.stdout


def test_drill_missing_db_fails(tmp_path):
    r = run(["bash", DRILL, "--db", str(tmp_path / "none.db"),
             "--out-dir", str(tmp_path / "out")])
    assert r.returncode != 0


def _make_db(path):
    con = sqlite3.connect(path)
    # verify_restore.py требует все ключевые таблицы (пустые — можно)
    for t in ("products", "orders", "users", "warehouses", "wh_stock",
              "wh_users", "settings", "sellers", "reviews"):
        con.execute(f"CREATE TABLE {t}(id INTEGER PRIMARY KEY, v TEXT)")
    con.executemany("INSERT INTO products(v) VALUES (?)", [("a",), ("b",)])
    con.execute("INSERT INTO orders(v) VALUES ('x')")
    con.commit()
    con.close()


def test_drill_full_on_synthetic_db(tmp_path):
    db = tmp_path / "live.db"
    _make_db(db)
    before = db.read_bytes()
    out = tmp_path / "out"
    r = run(["bash", DRILL, "--db", str(db), "--out-dir", str(out), "--checksum"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert (out / "REPORT.md").exists()
    assert (out / "MANIFEST.sha256").exists()
    report = (out / "REPORT.md").read_text()
    assert "пройдена" in report and "SHA-256" in report
    assert db.read_bytes() == before  # живая база не изменилась


def test_drill_detects_corrupt_snapshot(tmp_path):
    """Битый snapshot.db обязан провалить сверку (проверяем verify_restore напрямую)."""
    db = tmp_path / "live.db"
    _make_db(db)
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a sqlite file")
    r = run(["python3", str(ROOT / "telegram-shop" / "scripts" / "verify_restore.py"),
             str(bad), "--expect-live", str(db)])
    assert r.returncode != 0


# ---------- гигиена: mobile/build-apk.sh, install.sh, lock ----------
def test_mobile_build_help_no_download():
    r = run(["bash", MOBILE_BUILD, "--help"])
    assert r.returncode == 0 and "Магазин" in r.stdout
    assert run(["bash", MOBILE_BUILD, "--badopt"]).returncode != 0


def test_install_delegates_to_setup():
    r = run(["bash", INSTALL, "--help"])
    assert r.returncode == 0 and "--vps" in r.stdout  # текст setup.sh


def test_requirements_lock_exists():
    lock = ROOT / "telegram-shop" / "requirements-lock.txt"
    assert lock.exists()
    text = lock.read_text()
    assert "fastapi==" in text and "aiogram==" in text and "pytest==" in text


def test_no_stale_version_fallbacks():
    api = (ROOT / "telegram-shop" / "api.py").read_text()
    assert '"1.0.6"' not in api
    assert "1.1.0" in api
