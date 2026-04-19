import urllib.request, json, traceback

data = json.loads(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/participants').read())
pid = data[0]['id']
print('PID:', pid)

try:
    result = urllib.request.urlopen(f'http://127.0.0.1:8000/api/v1/participants/{pid}/finance/ml-insights')
    print(json.loads(result.read()))
except Exception as e:
    print('Error:', e)
    try:
        print('Body:', e.read().decode())
    except:
        pass
