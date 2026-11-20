#!/usr/bin/env python3
"""
Apply meta/entry_patches.json in place to the frozen aron7awol/mobe1969 output.

Those authors' pages and rows are never regenerated (see backfill_compare_links.py), so the
build's own re-application of the patches only reaches docs/database.json. This script brings
everything else into line: docs/database.json, docs/database.csv, the per-title pages
(heading, compare link, TMDb link) and the author index tables, then rebuilds docs/compare.

It is idempotent. Re-run it after editing meta/entry_patches.json, or after regenerating any
frozen content from upstream.

Page edits only happen when every entry on a page agrees on the old and the new value, so a
page that mixes titles is left alone and reported. Season/episode/edition patches change only
the data files: the page layout for those is decided at generation time.

    poetry run python scripts/apply_entry_patches.py [--dry-run]
"""
import argparse
import copy
import csv
import json
import os
import sys
from collections import defaultdict
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'beqcatalogue'), ROOT]
os.chdir(ROOT)

from keys import compute_compare_key  # noqa: E402
from patches import apply_entry_patches, load_patches  # noqa: E402
from scripts.backfill_compare_links import LINK_MARKER, insert_link, page_path  # noqa: E402

DB_JSON = 'docs/database.json'
DB_CSV = 'docs/database.csv'
FROZEN_AUTHORS = ('aron7awol', 'mobe1969')


def tmdb_path(e: dict) -> str:
    db_id = e.get('theMovieDB', '')
    return f"themoviedb.org/{'tv' if e.get('content_type') == 'TV' else 'movie'}/{db_id}" if db_id else ''


def compare_key(e: dict) -> str:
    return compute_compare_key(e['title'], e.get('content_type', ''), e.get('theMovieDB', ''), e.get('year', ''))


def one(values: set):
    return next(iter(values)) if len(values) == 1 else None


def patch_pages(before: dict, after: list[dict], log: list[str], dry_run: bool):
    '''before: id(entry) -> pre-patch copy, for patched frozen entries only'''
    pages = defaultdict(list)
    for e in after:
        if e.get('author') in FROZEN_AUTHORS and e.get('catalogue_url'):
            pages[(e['author'], page_path(e['catalogue_url']))].append(e)
    index_edits = defaultdict(list)  # author -> [(page, [(old, new)...])]
    for (author, page), entries in sorted(pages.items()):
        if not any(id(e) in before for e in entries):
            continue
        olds = [before.get(id(e), e) for e in entries]
        md = f'docs/{page}.md'
        if not os.path.exists(md):
            log.append(f'  missing page {md}')
            continue
        with open(md, encoding='utf-8') as f:
            content = f.read()
        updated = content
        subs = []  # applied to the index rows for this page too

        new_title = one({e['title'] for e in entries})
        if new_title:
            heading, _, body = updated.partition('\n')
            if heading != f'# {new_title}' and heading[2:] in {o['title'] for o in olds}:
                updated = f'# {new_title}\n{body}'
            for old_title in sorted({o['title'] for o in olds} - {new_title}):
                subs += [(f'[{old_title}', f'[{new_title}'), (f'={quote(old_title)}', f'={quote(new_title)}')]
        else:
            log.append(f'  {md}: mixed titles {sorted({e["title"] for e in entries})}, heading left alone')

        old_tm, new_tm = one({tmdb_path(o) for o in olds}), one({tmdb_path(e) for e in entries})
        if old_tm is not None and new_tm and old_tm != new_tm:
            if old_tm:
                updated = updated.replace(f'{old_tm})', f'{new_tm})')
                subs.append((f'{old_tm})', f'{new_tm})'))
            else:
                log.append(f'  {md}: TMDb id added in data only (page has no TMDb link to update)')

        old_ct, new_ct = one({o['content_type'] for o in olds}), one({e['content_type'] for e in entries})
        if old_ct and new_ct and old_ct != new_ct:
            subs.append((f'| {old_ct} |', f'| {new_ct} |'))

        old_key, new_key = one({compare_key(o) for o in olds}), one({compare_key(e) for e in entries})
        if new_key:
            if LINK_MARKER not in updated:  # backfill skipped pages whose entries disagreed
                updated = insert_link(updated, f'[{LINK_MARKER}](../compare/index.md?t={new_key})')
            elif old_key and old_key != new_key:
                updated = updated.replace(f'?t={old_key})', f'?t={new_key})')
        else:
            log.append(f'  {md}: entries disagree on compare key, link left alone')

        if updated != content:
            log.append(f'  page {md}')
            if not dry_run:
                with open(md, 'w', encoding='utf-8') as f:
                    f.write(updated)
        if subs:
            index_edits[author].append((page, subs))

    for author, edits in index_edits.items():
        idx = f'docs/{author}.md'
        with open(idx, encoding='utf-8') as f:
            lines = f.read().split('\n')
        changed = 0
        for page, subs in edits:
            link = f'(./{page}.md'
            for i, line in enumerate(lines):
                if line.startswith('| [') and link in line:
                    new_line = line
                    for old, new in subs:
                        new_line = new_line.replace(old, new)
                    if new_line != line:
                        lines[i] = new_line
                        changed += 1
        log.append(f'  index {idx}: {changed} rows')
        if changed and not dry_run:
            with open(idx, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))


def patch_csv(before: dict, after: list[dict], log: list[str], dry_run: bool):
    renames = {}
    for e in after:
        o = before.get(id(e))
        if o and o['title'] != e['title']:
            renames[(e['author'], e['catalogue_url'], o['title'])] = e['title']
    if not renames:
        return
    with open(DB_CSV, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    changed = 0
    for r in rows[1:]:
        new = renames.get((r[3], r[5], r[0])) if len(r) > 5 else None
        if new:
            r[0] = new
            changed += 1
    log.append(f'  {DB_CSV}: {changed} rows')
    if changed and not dry_run:
        with open(DB_CSV, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true', help='report what would change without writing')
    args = parser.parse_args()

    with open(DB_JSON, encoding='utf-8') as f:
        catalogue = json.load(f)
    pristine = {id(e): copy.deepcopy(e) for e in catalogue if e.get('author') in FROZEN_AUTHORS}
    report = apply_entry_patches(catalogue, load_patches())
    print(report.summary())
    patched_ids = {id(e) for e in catalogue if id(e) in pristine and e != pristine[id(e)]}
    before = {i: pristine[i] for i in patched_ids}
    if not before:
        print('Nothing to change')
        return

    log = []
    patch_pages(before, catalogue, log, args.dry_run)
    patch_csv(before, catalogue, log, args.dry_run)
    print('\n'.join(log))
    if args.dry_run:
        print('Dry run, nothing written')
        return

    with open(DB_JSON, 'w') as f:
        json.dump(catalogue, f, indent=0)
    from beqcatalogue import build_compare_data
    build_compare_data(catalogue)


if __name__ == '__main__':
    main()
