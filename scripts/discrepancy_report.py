#!/usr/bin/env python3
"""
Find catalogue entries whose metadata disagrees with other entries for the same release.

Each mismatch stops ezbeq treating the entries as the same title. Four checks:

* contentType: one TMDb id + title filed as both film and TV. When any TV entry has a season the
  film entries are flagged as the likely fix, otherwise the season-less TV entries are.
* titles: one TMDb id + content type, titles differing beyond case. Classified as
  'Punctuation / spelling' (equal after folding accents, punctuation and a leading 'The'),
  'Title variant' (one contains the other or they are close, similarity >= 0.75) or
  'Different title, check TMDb id' (unrelated titles or differing years).
* blankSeason: TV entries with no season.
* noTmdb: entries with no TMDb id.

Film/TV pairs that share a TMDb number but not a title are ignored: TMDb numbers movies and
shows separately.

    python scripts/discrepancy_report.py [docs/database.json] > report.json
"""
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from difflib import SequenceMatcher

KINDS = ['Different title, check TMDb id', 'Title variant', 'Punctuation / spelling']


def fold(title: str) -> str:
    t = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode('ascii').casefold()
    t = re.sub(r'[^a-z0-9]+', ' ', t).strip()
    return t[4:] if t.startswith('the ') else t


def row(e: dict, **extra) -> dict:
    return {'author': e['author'], 'title': e['title'], 'year': e.get('year', ''), 'type': e['content_type'],
            'season': e.get('season', '') or '', 'tmdb': e.get('theMovieDB', '') or '',
            'audio': ', '.join(e.get('audioTypes', [])), 'edition': e.get('edition', '') or '',
            'url': e.get('catalogue_url', ''), **extra}


def sort_key(title: str):
    t = title.casefold()
    return t[4:] if t.startswith('the ') else t


def by_author(r: dict):
    return r['author'].casefold(), r['title'].casefold()


def classify(entries: list[dict]) -> str:
    folded = {fold(e['title']) for e in entries}
    if len(folded) == 1:
        return KINDS[2]
    if len({e.get('year', '') for e in entries}) > 1:
        return KINDS[0]
    ts = sorted(folded)
    for i, a in enumerate(ts):
        for b in ts[i + 1:]:
            if not (a in b or b in a or SequenceMatcher(None, a, b).ratio() >= 0.75):
                return KINDS[0]
    return KINDS[1]


def build(db: list[dict]) -> dict:
    by_id_title = defaultdict(list)
    by_id_type = defaultdict(list)
    for e in db:
        if e.get('theMovieDB'):
            by_id_title[(e['theMovieDB'], e['title'].casefold())].append(e)
            by_id_type[(e['theMovieDB'], e['content_type'])].append(e)

    content_type = []
    for (tmdb, _), es in by_id_title.items():
        if len({e['content_type'] for e in es}) < 2:
            continue
        tv_has_season = any(e['content_type'] == 'TV' and e.get('season') for e in es)
        fix = (lambda e: e['content_type'] == 'film') if tv_has_season else \
            (lambda e: e['content_type'] == 'TV' and not e.get('season'))
        content_type.append({'tmdb': tmdb, 'title': es[0]['title'], 'entries': [row(e, fix=fix(e)) for e in es]})
    content_type.sort(key=lambda g: sort_key(g['title']))
    flagged = {r['url'] for g in content_type for r in g['entries'] if r['fix']}

    titles = []
    for (tmdb, ctype), es in by_id_type.items():
        if len({e['title'].casefold() for e in es}) < 2:
            continue
        titles.append({'tmdb': tmdb, 'type': ctype, 'kind': classify(es),
                       'titles': sorted({e['title'] for e in es}, key=str.casefold),
                       'entries': [row(e) for e in es]})
    titles.sort(key=lambda g: (KINDS.index(g['kind']), g['titles'][0].casefold()))

    return {
        'generated': date.today().isoformat(),
        'total': len(db),
        'contentType': content_type,
        'titles': titles,
        # season-less TV entries already listed as film/TV mix-ups are left out here
        'blankSeason': sorted((row(e) for e in db if e['content_type'] == 'TV' and not e.get('season')
                               and e.get('catalogue_url') not in flagged), key=by_author),
        'noTmdb': sorted((row(e) for e in db if not e.get('theMovieDB')), key=by_author),
    }


if __name__ == '__main__':
    with open(sys.argv[1] if len(sys.argv) > 1 else 'docs/database.json', encoding='utf-8') as f:
        json.dump(build(json.load(f)), sys.stdout, ensure_ascii=False, separators=(',', ':'))
