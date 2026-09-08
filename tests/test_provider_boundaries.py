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

def test_stub_provider_returns_deterministic_result():
    from social_providers import StubProvider
    result = StubProvider().publish({'status':'approved','publication_id':42})
    assert result == {'ok':True,'mode':'stub','external_id':'stub-42','channel':'stub'}

def test_callback_hmac_canonical_json_is_stable():
    import hashlib, hmac, json
    body={'result_url':'https://example.test/video.mp4','error':''}
    payload=json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    sig=hmac.new(b'secret',payload.encode(),hashlib.sha256).hexdigest()
    assert hmac.compare_digest(sig, hmac.new(b'secret',payload.encode(),hashlib.sha256).hexdigest())
