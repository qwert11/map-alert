"""Выкачивает участок истории публичного канала: посты с id < start, пока не дойдёт до id <= stop.

python scripts/collect_range.py <канал> <start_id> <stop_id> <выход.jsonl>
Нужен, чтобы качать длинную историю (с 2022) несколькими процессами параллельно; дописывает
в выходной файл по странице, поэтому переживает обрыв — при перезапуске продолжает с самого старого id в файле.
"""
import json, os, sys, time
from collect_tg import fetch, parse


def main():
    ch, start, stop, path = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    before = start
    if os.path.exists(path):
        ids = [json.loads(l)['id'] for l in open(path, encoding='utf-8') if l.strip()]
        if ids:
            before = min(ids)
    with open(path, 'a', encoding='utf-8') as f:
        while before > stop:
            posts = parse(fetch(f'https://t.me/s/{ch}?before={before}'))
            posts = [p for p in posts if p['id'] < before]
            if not posts:
                before -= 20  # пустая страница (удалённые посты) — шагаем дальше
                continue
            for p in posts:
                if p['id'] > stop:
                    f.write(json.dumps(p, ensure_ascii=False) + '\n')
            f.flush()
            before = min(p['id'] for p in posts)
            print(ch, before, posts[0]['dt'][:10], flush=True)
            time.sleep(1.0)
    print('done', ch, start, stop, flush=True)


if __name__ == '__main__':
    main()
