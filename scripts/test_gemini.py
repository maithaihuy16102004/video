import urllib.request, json, sys
sys.path.insert(0, '.')
from pipeline.env_secrets import get_gemini_api_key, load_dotenv
load_dotenv()
key = get_gemini_api_key()
for model in ['gemini-flash-latest', 'gemini-flash-lite-latest', 'gemini-1.5-flash-latest']:
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}'
    body = json.dumps({'contents': [{'parts': [{'text': 'Hello'}]}]}).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res = json.loads(resp.read().decode('utf-8'))
            print(f'{model} SUCCESS:', res['candidates'][0]['content']['parts'][0]['text'][:40])
            break
    except Exception as e:
        print(f'{model} ERROR:', e)
