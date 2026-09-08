from urllib.parse import parse_qs, urlsplit

def build(url, source, medium='social', campaign='', content=''):
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    if not url.startswith(('https://','http://')): raise ValueError
    p=urlsplit(url); q=dict(parse_qsl(p.query, keep_blank_values=True))
    q.update({k:v for k,v in [('utm_source',source),('utm_medium',medium),('utm_campaign',campaign),('utm_content',content)] if v})
    return urlunsplit((p.scheme,p.netloc,p.path,urlencode(q),p.fragment))

def test_utm_preserves_existing_query_and_fragment():
    result=build('https://example.test/p?a=1#top','telegram',campaign='sale')
    q=parse_qs(urlsplit(result).query)
    assert q['a']==['1']; assert q['utm_source']==['telegram']; assert q['utm_campaign']==['sale']; assert urlsplit(result).fragment=='top'

def test_utm_rejects_non_http():
    try: build('javascript:alert(1)','x')
    except ValueError: return
    assert False

def test_utm_rejects_missing_scheme():
    try: build('//example.test/path','x')
    except ValueError: return
    assert False
