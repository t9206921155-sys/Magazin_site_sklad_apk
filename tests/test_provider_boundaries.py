from social_providers import TelegramProvider
from telegram_shop.wildberries_provider import WildberriesProvider


def test_social_provider_disabled_without_credentials():
    assert TelegramProvider().validate()["enabled"] is False


def test_wildberries_is_disabled_without_audit():
    provider = WildberriesProvider()
    status = provider.audit_status()
    assert status["publishing"] == "disabled"
    assert status["scraping"] is False
