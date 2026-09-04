#!/usr/bin/env python3
"""Smoke tests for marketplace catalog filters."""
import json, urllib.parse, urllib.request
BASE='http://127.0.0.1:8000'
def get(path):
    with urllib.request.urlopen(BASE+path, timeout=10) as r: return r.status, json.load(r)
checks=[('/api/catalog',None),('/api/catalog?price_min=0&price_max=999999',None),('/api/catalog?sort=price_asc',None),('/api/catalog?q=%25%3C%3E',None)]
for path,_ in checks:
    status,data=get(path); assert status==200 and isinstance(data.get('products'),list), path
print(f'{len(checks)} passed, 0 failed')
