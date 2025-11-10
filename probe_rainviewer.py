import json,urllib.request,sys
maps_url='https://api.rainviewer.com/public/weather-maps.json'
print('Fetching',maps_url)
req=urllib.request.Request(maps_url,headers={'User-Agent':'Python-probe/1.0'})
try:
    data=urllib.request.urlopen(req,timeout=10).read()
except Exception as e:
    print('Failed to fetch maps.json:',e); sys.exit(1)
j=json.loads(data)
host=j.get('host')
paths=[p.get('path') for p in j.get('radar',{}).get('past',[])]
print('host=',host)
print('found',len(paths),'paths. sample:',paths[:5])
# try patterns
candidates=[]
for p in paths[:8]:
    candidates.append(host + p + '.png')
    candidates.append(host + p + '/radar.png')
    candidates.append(host + p + '/radar.gif')
    candidates.append(host + p + '/tiles/radar.png')
    candidates.append(host + p + '/0/0/0.png')
    candidates.append(host + p + '/256/256/0/0.png')

print('\nTesting candidate URLs...')
for url in candidates:
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Python-probe/1.0'})
        with urllib.request.urlopen(req,timeout=10) as r:
            code=r.getcode(); ctype=r.info().get('Content-Type')
            print('OK',url,code,ctype)
            b=r.read(64)
            print('First bytes:',b[:8])
            # print only first success
            break
    except Exception as e:
        print('bad',url,':',e)
else:
    print('No candidate succeeded')
