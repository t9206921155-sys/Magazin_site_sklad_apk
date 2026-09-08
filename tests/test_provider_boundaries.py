import importlib.util
from social_providers import TelegramProvider
spec=importlib.util.spec_from_file_location("wb", "telegram-shop/wildberries_provider.py")
wb=importlib.util.module_from_spec(spec); spec.loader.exec_module(wb)
WildberriesProvider=wb.WildberriesProvider


def test_social_provider_disabled_without_credentials():
    assert TelegramProvider().validate()["ok"] is False


def test_wildberries_is_disabled_without_audit():
    provider = WildberriesProvider()
    status = provider.audit_status()
    assert status["publishing"] == "disabled"
    assert status["scraping"] is False

def test_dry_run_requires_approval():
    provider = TelegramProvider()
    try:
        provider.dry_run({'status':'draft','publication_id':1})
    except ValueError:
        return
    assert False

def test_diagnostics_exposes_safe_dry_run_state():
    data = TelegramProvider().diagnostics()
    assert data['enabled'] is False
    assert data['dry_run'] is True
    assert data['publishing'] == 'disabled'
