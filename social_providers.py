"""Official social publishing provider boundaries; no scraping or unofficial automation."""
class SocialProvider:
    channel='base'
    def __init__(self, token=''): self.token=str(token or '').strip()
    @property
    def enabled(self): return bool(self.token)
    def validate(self): return {'ok':self.enabled,'channel':self.channel,'error':'' if self.enabled else 'credentials not configured'}
    def publish(self, package): raise NotImplementedError('Official adapter required before publishing')

class TelegramProvider(SocialProvider): channel='telegram'
class VKProvider(SocialProvider): channel='vk'
class AvitoProvider(SocialProvider): channel='avito'
class InstagramProvider(SocialProvider): channel='instagram'
class TikTokProvider(SocialProvider): channel='tiktok'
