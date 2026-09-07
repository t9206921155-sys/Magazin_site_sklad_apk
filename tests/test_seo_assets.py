from pathlib import Path

API = Path('telegram-shop/api.py').read_text()

def test_seo_routes_exist():
    assert '@app.get("/robots.txt")' in API
    assert '@app.get("/sitemap.xml")' in API

def test_seo_metadata_helpers_exist():
    for token in ('canonical', 'og_image', 'jsonld', 'title', 'description'):
        assert token in API

def test_sitemap_has_product_and_category_urls():
    assert 'store.products()' in API
    assert 'store.categories()' in API
