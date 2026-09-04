import cloudstore
from storage_contracts import PhotoStorage, DatabaseProvider, provider_status

# Configuration-only contract checks; no network and no credentials.
s3 = cloudstore.S3Client('', '', '', '')
yd = cloudstore.YandexDiskClient('', 'app:/test')
assert isinstance(s3, PhotoStorage) and isinstance(yd, PhotoStorage)
assert provider_status(s3)['ok'] is False
assert provider_status(yd)['ok'] is False
print('storage contracts: 4 passed, 0 failed')
