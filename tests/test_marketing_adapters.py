from marketing_adapters import ADAPTERS, CredentialsMissing

def test_all_required_channels_have_safe_adapter():
    assert set(ADAPTERS) == {'telegram','vk','avito','instagram','tiktok','wildberries'}
    assert all(cls().diagnostics()['dry_run'] for cls in ADAPTERS.values())

def test_publish_is_disabled_without_credentials():
    for cls in ADAPTERS.values():
        try: cls().validate_credentials()
        except CredentialsMissing: pass
        else: assert False

def test_dry_run_is_deterministic():
    for channel, cls in ADAPTERS.items():
        result=cls().dry_run({'status':'approved','publication_id':7})
        assert result['channel']==channel and result['external_id']=='dry-7'

def test_registry_reads_environment_without_exposing_tokens():
    from marketing_adapter_registry import registry_from_env, diagnostics
    adapters=registry_from_env({'TELEGRAM_ADAPTER_TOKEN':'secret','TELEGRAM_ADAPTER_ACCOUNT_ID':'channel'})
    assert adapters['telegram'].enabled is True
    data=diagnostics({'TELEGRAM_ADAPTER_TOKEN':'secret','TELEGRAM_ADAPTER_ACCOUNT_ID':'channel'})
    assert 'secret' not in str(data)
    assert data['telegram']['enabled'] is True
