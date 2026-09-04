#!/usr/bin/env python3
import json, sys, urllib.request
base=(sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8000').rstrip('/')
def get(path):
    r=urllib.request.urlopen(base+path,timeout=10); return r.status,json.load(r)
st,live=get('/health/live'); assert st==200 and live.get('ok') is True
st,ready=get('/health/ready'); assert st==200 and ready.get('ok') is True and ready['checks']['database'] is True
print('health: 2 passed, 0 failed')
