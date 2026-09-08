"""Environment-backed adapter registry. Real transports remain disabled until implemented."""
import os
from marketing_adapters import ADAPTERS

ENV_PREFIX = {
    'telegram': 'TELEGRAM_ADAPTER', 'vk': 'VK_ADAPTER', 'avito': 'AVITO_ADAPTER',
    'instagram': 'META_ADAPTER', 'tiktok': 'TIKTOK_ADAPTER', 'wildberries': 'WILDBERRIES_ADAPTER'
}

def registry_from_env(env=None):
    env = os.environ if env is None else env
    result = {}
    for channel, cls in ADAPTERS.items():
        prefix = ENV_PREFIX[channel]
        result[channel] = cls(env.get(prefix + '_TOKEN', ''), env.get(prefix + '_ACCOUNT_ID', ''))
    return result

def diagnostics(env=None):
    return {channel: adapter.diagnostics() for channel, adapter in registry_from_env(env).items()}
