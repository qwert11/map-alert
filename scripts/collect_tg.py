"""Выкачивает посты публичных Telegram-каналов через t.me/s/<канал>?before=<id>.

python scripts/collect_tg.py <канал> <YYYY-MM-DD от> [выход.jsonl]
Идёт от свежих постов назад, пока не дойдёт до даты «от» (UTC).
Дописывает только новые посты (по id), поэтому можно перезапускать.
"""
import json, os, re, sys, time, html, subprocess

def fetch(url):
    for attempt in range(6):
        r = subprocess.run(['curl', '-s', '-m', '30', '-A', 'Mozilla/5.0', '-w', '\n%{http_code}', url],
                           capture_output=True)
        body, _, code = r.stdout.rpartition(b'\n')
        if code == b'200' and body:
            return body.decode('utf-8', 'replace')
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f'fetch failed {url} code={code}')

def parse(s):
    out = []
    for blk in s.split('tgme_widget_message_wrap')[1:]:
        p = re.search(r'data-post="([^"]+)"', blk)
        d = re.search(r'<time datetime="([^"]+)"', blk)
        if not p or not d:
            continue
        t = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', blk, re.S)
        txt = ''
        if t:
            txt = re.sub(r'<br\s*/?>', '\n', t.group(1))
            txt = html.unescape(re.sub(r'<[^>]+>', '', txt)).strip()
        out.append({'id': int(p.group(1).split('/')[1]), 'dt': d.group(1), 'text': txt})
    return out

def main():
    ch, since = sys.argv[1], sys.argv[2]
    path = sys.argv[3] if len(sys.argv) > 3 else f'_tmp/tg/{ch}.jsonl'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    have = {}
    if os.path.exists(path):
        for line in open(path, encoding='utf-8'):
            x = json.loads(line); have[x['id']] = x
    prev = set(have)
    url = f'https://t.me/s/{ch}'
    new = 0
    while True:
        posts = parse(fetch(url))
        if not posts:
            break
        for x in posts:
            if x['id'] not in have:
                have[x['id']] = x; new += 1
        oldest = min(posts, key=lambda x: x['id'])
        print(ch, oldest['dt'], len(have), flush=True)
        if oldest['dt'][:10] < since:
            break
        # дошли до скачанного раньше участка — прыгаем к его началу
        nxt = min(prev) if any(x['id'] in prev for x in posts) else oldest['id']
        url = f'https://t.me/s/{ch}?before={nxt}'
        time.sleep(1.2)
    with open(path, 'w', encoding='utf-8') as f:
        for k in sorted(have):
            f.write(json.dumps(have[k], ensure_ascii=False) + '\n')
    print('done', ch, 'new', new, 'total', len(have), flush=True)

if __name__ == '__main__':
    main()
