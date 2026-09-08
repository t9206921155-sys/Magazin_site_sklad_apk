"""Safe official-adapter scaffolding.
No network calls are made until a concrete official transport is supplied.
"""
import time

class AdapterError(Exception): pass
class CredentialsMissing(AdapterError): pass

class OfficialAdapter:
    channel = 'base'
    def __init__(self, token='', account_id=''):
        self.token = str(token or '').strip(); self.account_id = str(account_id or '').strip()
    def diagnostics(self):
        return {'channel': self.channel, 'enabled': bool(self.token and self.account_id), 'transport': 'disabled', 'dry_run': True}
    def validate_credentials(self):
        if not self.token or not self.account_id: raise CredentialsMissing(f'{self.channel}: credentials required')
        return True
    def dry_run(self, package):
        if package.get('status') not in ('approved','published'): raise AdapterError('approved package required')
        return {'ok': True, 'mode': 'dry-run', 'channel': self.channel, 'external_id': f'dry-{package.get("publication_id", "unknown")}', 'attempts': 0}
    def publish(self, package):
        raise AdapterError(f'{self.channel}: official transport is not configured')
    def retry_delay(self, attempt): return min(60, 2 ** max(0, int(attempt)))

class TelegramAdapter(OfficialAdapter): channel='telegram'
class VKAdapter(OfficialAdapter): channel='vk'
class AvitoAdapter(OfficialAdapter): channel='avito'
class MetaInstagramAdapter(OfficialAdapter): channel='instagram'
class TikTokAdapter(OfficialAdapter): channel='tiktok'
class WildberriesAdapter(OfficialAdapter): channel='wildberries'

ADAPTERS = {x.channel:x for x in (TelegramAdapter, VKAdapter, AvitoAdapter, MetaInstagramAdapter, TikTokAdapter, WildberriesAdapter)}
