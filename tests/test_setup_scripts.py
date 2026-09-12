"""Блок 28: установка «из коробки» — офлайн-тесты скриптов.

Проверяются только --help/--dry-run/--check и генерация .env во временный
каталог (SETUP_ENV_FILE). Без сети, без sudo, боевой .env не трогается.
"""
import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETUP_ENV = str(ROOT / "deploy" / "setup-env.sh")
SETUP_BOT = str(ROOT / "telegram-shop" / "scripts" / "setup_bot.py")
BUILD_APPS = str(ROOT / "deploy" / "build-apps.sh")
SETUP = str(ROOT / "setup.sh")
UPDATE = str(ROOT / "deploy" / "update.sh")
BOOTSTRAP = str(ROOT / "deploy" / "bootstrap-vps.sh")

TOKEN = "1234567890:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
REQUIRED_KEYS = ["BOT_TOKEN", "ADMIN_IDS", "ADMIN_PASSWORD", "WEBAPP_URL",
                 "PAYMENT_PROVIDER", "BOT_MODE", "WEBHOOK_PATH", "WEBHOOK_SECRET",
                 "HOST", "PORT", "CORS_ORIGINS", "METRICS_TOKEN", "AUTH_RATE_LIMIT",
                 "TRUSTED_HOSTS", "RATE_LIMIT_1C", "RATE_LIMIT_API",
                 "WH_SESSION_TTL_DAYS", "DISK_FREE_MIN_MB"]


def run(cmd, env=None, **kw):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(cmd, capture_output=True, text=True, env=e, **kw)


def read_env(path):
    data = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    return data


# ---------- setup-env.sh ----------
def test_setup_env_help():
    r = run(["bash", SETUP_ENV, "--help"])
    assert r.returncode == 0 and ".env" in r.stdout


def test_setup_env_generate_noninteractive(tmp_path):
    env_file = tmp_path / ".env"
    r = run(["bash", SETUP_ENV, "--non-interactive",
             "--domain", "https://shop.example/",
             "--bot-token", TOKEN,
             "--admin-ids", "111,222",
             "--payment", "test", "--bot-mode", "polling"],
            env={"SETUP_ENV_FILE": str(env_file)})
    assert r.returncode == 0, r.stderr
    data = read_env(env_file)
    for k in REQUIRED_KEYS:
        assert k in data, k
    assert data["WEBAPP_URL"] == "https://shop.example"
    assert data["CORS_ORIGINS"] == "https://shop.example"
    assert data["TRUSTED_HOSTS"] == "shop.example"
    assert data["BOT_TOKEN"] == TOKEN
    assert data["ADMIN_IDS"] == "111,222"
    assert len(data["ADMIN_PASSWORD"]) >= 12  # сгенерирован
    assert len(data["METRICS_TOKEN"]) == 32 and len(data["WEBHOOK_SECRET"]) == 32
    # секреты замаскированы в выводе
    assert TOKEN not in r.stdout and TOKEN not in r.stderr
    assert data["ADMIN_PASSWORD"] in (r.stdout + r.stderr)  # пароль показывают 1 раз
    # права 600
    assert stat.S_IMODE(os.stat(env_file).st_mode) == 0o600


def test_setup_env_idempotent_without_force(tmp_path):
    env_file = tmp_path / ".env"
    env = {"SETUP_ENV_FILE": str(env_file)}
    run(["bash", SETUP_ENV, "--non-interactive", "--admin-password", "keepme123456"],
        env=env, check=True)
    r = run(["bash", SETUP_ENV, "--non-interactive", "--admin-password", "other123456789"],
            env=env)
    assert r.returncode == 0
    assert read_env(env_file)["ADMIN_PASSWORD"] == "keepme123456"


def test_setup_env_force_overwrites(tmp_path):
    env_file = tmp_path / ".env"
    env = {"SETUP_ENV_FILE": str(env_file)}
    run(["bash", SETUP_ENV, "--non-interactive", "--admin-password", "keepme123456"],
        env=env, check=True)
    r = run(["bash", SETUP_ENV, "--non-interactive", "--force",
             "--admin-password", "other123456789"], env=env)
    assert r.returncode == 0, r.stderr
    assert read_env(env_file)["ADMIN_PASSWORD"] == "other123456789"


def test_setup_env_check_ok_and_fail(tmp_path):
    env_file = tmp_path / ".env"
    env = {"SETUP_ENV_FILE": str(env_file)}
    run(["bash", SETUP_ENV, "--non-interactive", "--bot-token", TOKEN], env=env, check=True)
    assert run(["bash", SETUP_ENV, "--check"], env=env).returncode == 0
    env_file.write_text("BOT_TOKEN=bad\n")
    assert run(["bash", SETUP_ENV, "--check"], env=env).returncode != 0
    assert run(["bash", SETUP_ENV, "--check"],
               env={"SETUP_ENV_FILE": str(tmp_path / "none.env")}).returncode != 0


def test_setup_env_rejects_bad_values(tmp_path):
    env = {"SETUP_ENV_FILE": str(tmp_path / ".env")}
    assert run(["bash", SETUP_ENV, "--non-interactive", "--bot-token", "bad"],
               env=env).returncode != 0
    assert run(["bash", SETUP_ENV, "--non-interactive", "--admin-ids", "abc"],
               env=env).returncode != 0
    assert run(["bash", SETUP_ENV, "--non-interactive", "--payment", "nope"],
               env=env).returncode != 0
    assert run(["bash", SETUP_ENV, "--non-interactive", "--bot-mode", "nope"],
               env=env).returncode != 0


def test_setup_env_dry_run_writes_nothing(tmp_path):
    env_file = tmp_path / ".env"
    r = run(["bash", SETUP_ENV, "--dry-run", "--non-interactive",
             "--bot-token", TOKEN], env={"SETUP_ENV_FILE": str(env_file)})
    assert r.returncode == 0 and not env_file.exists()
    assert TOKEN not in r.stdout  # маскировка и в dry-run


def test_setup_env_webhook_fallback_local(tmp_path):
    env_file = tmp_path / ".env"
    r = run(["bash", SETUP_ENV, "--non-interactive", "--force",
             "--bot-mode", "webhook", "--bot-token", TOKEN],
            env={"SETUP_ENV_FILE": str(env_file)})
    assert r.returncode == 0
    assert read_env(env_file)["BOT_MODE"] == "polling"  # без https-домена


def test_setup_env_via_setup_vars(tmp_path):
    env_file = tmp_path / ".env"
    r = run(["bash", SETUP_ENV, "--non-interactive"], env={
        "SETUP_ENV_FILE": str(env_file), "SETUP_DOMAIN": "s.ru",
        "SETUP_BOT_TOKEN": TOKEN, "SETUP_ADMIN_IDS": "777"})
    assert r.returncode == 0, r.stderr
    data = read_env(env_file)
    assert data["WEBAPP_URL"] == "https://s.ru" and data["ADMIN_IDS"] == "777"


# ---------- setup_bot.py (stdlib, dry-run без сети) ----------
def test_setup_bot_help():
    r = run(["python3", SETUP_BOT, "--help"])
    assert r.returncode == 0 and "getMe" in r.stdout


def test_setup_bot_dry_run(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(f"BOT_TOKEN={TOKEN}\nWEBAPP_URL=https://s.ru\nBOT_MODE=webhook\n"
                        "WEBHOOK_PATH=/tg/webhook\nWEBHOOK_SECRET=sec\nADMIN_IDS=111,222\n")
    r = run(["python3", SETUP_BOT, "--env", str(env_file), "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "setMyCommands" in r.stdout and "setWebhook" in r.stdout
    assert "111, 222" in r.stdout
    assert TOKEN not in r.stdout  # токен маскируется


def test_setup_bot_rejects_bad_token(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("BOT_TOKEN=bad\n")
    r = run(["python3", SETUP_BOT, "--env", str(env_file), "--dry-run"])
    assert r.returncode != 0
    r = run(["python3", SETUP_BOT, "--env", str(tmp_path / "none.env"), "--dry-run"])
    assert r.returncode != 0


def test_setup_bot_commands_match_bot_py():
    """Команды из setup_bot.py обязаны существовать в bot.py."""
    bot_src = (ROOT / "telegram-shop" / "bot.py").read_text()
    src = Path(SETUP_BOT).read_text()
    import re
    for cmd in re.findall(r'\("([a-z_]+)",', src.split("PUBLIC_COMMANDS")[1].split("]")[0]):
        assert f'Command("{cmd}")' in bot_src, cmd


# ---------- build-apps.sh ----------
def test_build_apps_help():
    r = run(["bash", BUILD_APPS, "--help"])
    assert r.returncode == 0 and "Склад" in r.stdout


def test_build_apps_dry_run():
    r = run(["bash", BUILD_APPS, "--dry-run", "--url", "https://s.ru"])
    assert r.returncode == 0, r.stderr
    assert "Склад" in r.stdout and "Магазин" in r.stdout
    r = run(["bash", BUILD_APPS, "--dry-run", "--sklad-only"])
    assert r.returncode == 0 and "Магазин" not in r.stdout


def test_build_apps_rejects_bad_url_and_flags():
    assert run(["bash", BUILD_APPS, "--url", "notaurl"]).returncode != 0
    assert run(["bash", BUILD_APPS, "--sklad-only", "--shop-only"]).returncode != 0
    assert run(["bash", BUILD_APPS, "--nope"]).returncode != 0


# ---------- setup.sh / update.sh / bootstrap ----------
def test_setup_help_and_dry_run():
    r = run(["bash", SETUP, "--help"])
    assert r.returncode == 0 and "--vps" in r.stdout
    r = run(["bash", SETUP, "--dry-run", "--non-interactive",
             "--bot-token", TOKEN, "--domain", "s.ru"],
            env={"SETUP_ENV_FILE": "/tmp/nonexistent-setup-test.env"})
    assert r.returncode == 0, r.stderr
    assert TOKEN not in r.stdout  # маскировка сквозная


def test_update_and_bootstrap_help():
    assert run(["bash", UPDATE, "--help"]).returncode == 0
    assert run(["bash", BOOTSTRAP, "--help"]).returncode == 0
    r = run(["bash", UPDATE, "--dry-run"], env={"DEPLOY_DOMAIN": "https://s.ru"})
    assert r.returncode == 0 and "smoke" in r.stdout


def test_scripts_bash_syntax():
    for sh in (SETUP, SETUP_ENV, BUILD_APPS, UPDATE, BOOTSTRAP,
               str(ROOT / "install.sh"), str(ROOT / "build-distr.sh")):
        r = run(["bash", "-n", sh])
        assert r.returncode == 0, sh
