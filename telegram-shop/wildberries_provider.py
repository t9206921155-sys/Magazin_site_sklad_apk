"""Official Wildberries provider boundary; scraping is intentionally unsupported."""
import json
import urllib.request

class WildberriesProvider:
    def __init__(self, token="", base_url="https://content-api.wildberries.ru"):
        self.token=str(token or '').strip(); self.base_url=base_url.rstrip('/')
    @property
    def enabled(self): return bool(self.token)
    def ping(self):
        if not self.enabled: return {"ok":False,"error":"Wildberries API token is not configured"}
        return {"ok":False,"error":"Official account/API capability must be verified before activation"}
    def map_product(self, product):
        return {"vendorCode": str(product.get("code") or product.get("id")), "title": product.get("name",""), "price": int(product.get("price",0) or 0), "description": product.get("description","")}
    def publish(self, product):
        raise RuntimeError("Wildberries publishing is disabled until official API/account audit is complete")
