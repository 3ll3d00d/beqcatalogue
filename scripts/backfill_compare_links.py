#!/usr/bin/env python3
"""
One-time backfill for aron7awol and mobe1969.

Their pages are frozen (excluded from the main generation pipeline as a build-speed
optimisation, since those authors no longer publish new content) so they never picked
up the "Compare across authors" link that beqcatalogue/__init__.py now adds for every
other author. This inserts a single page-level link into each frozen page without
regenerating or otherwise touching the rest of its content.

A page-level (rather than per-format-section) link is sufficient because the compare
key only depends on title/theMovieDB/year, which is constant across a page's formats.
Pages where entries disagree on those fields (pre-existing data quirks, ~18 of ~8500)
are skipped rather than guessing which link is correct.
"""
import json
from collections import defaultdict

from beqcatalogue import compute_compare_key

DB_PATH = 'docs/database.json'
FROZEN_AUTHORS = ('aron7awol', 'mobe1969')
LINK_MARKER = 'Compare across authors'
URL_PREFIX = 'https://beqcatalogue.readthedocs.io/en/latest/'


def page_path(catalogue_url: str) -> str:
    rest = catalogue_url[len(URL_PREFIX):]
    rest = rest.split('#')[0]
    if rest.endswith('/'):
        rest = rest[:-1]
    return rest


def insert_link(content: str, link_line: str) -> str:
    lines = content.split('\n')
    insert_at = 1  # right after the '# Title' heading
    if len(lines) > 2 and lines[2].startswith('* Author:'):
        insert_at = 3  # TV pages also carry a '* Author: ...' line
    header = lines[:insert_at]
    rest = lines[insert_at:]
    while rest and rest[0].strip() == '':
        rest.pop(0)
    return '\n'.join(header + ['', link_line, ''] + rest)


def main():
    with open(DB_PATH) as f:
        data = json.load(f)

    pages = defaultdict(list)
    for e in data:
        if e.get('author') in FROZEN_AUTHORS and e.get('catalogue_url'):
            pages[page_path(e['catalogue_url'])].append(e)

    patched, skipped_ambiguous, skipped_existing, skipped_missing = 0, [], 0, 0

    for page, entries in sorted(pages.items()):
        titles = set(e.get('title', '') for e in entries)
        tmdbs = set(e.get('theMovieDB', '') for e in entries)
        content_types = set(e.get('content_type', '') for e in entries)
        if len(titles) > 1 or len(tmdbs) > 1 or len(content_types) > 1:
            skipped_ambiguous.append(page)
            continue

        sample = entries[0]
        key = compute_compare_key(sample['title'], sample.get('content_type', ''),
                                  sample.get('theMovieDB', ''), sample.get('year', ''))
        md_path = f'docs/{page}.md'
        try:
            with open(md_path) as f:
                content = f.read()
        except FileNotFoundError:
            skipped_missing += 1
            continue

        if LINK_MARKER in content:
            skipped_existing += 1
            continue

        link_line = f"[Compare across authors](../compare/index.md?t={key})"
        with open(md_path, 'w') as f:
            f.write(insert_link(content, link_line))
        patched += 1

    print(f"Patched {patched} pages")
    print(f"Skipped {len(skipped_ambiguous)} ambiguous pages (differing title/theMovieDB/content_type):")
    for p in skipped_ambiguous:
        print(f"  {p}")
    print(f"Skipped {skipped_existing} pages that already had a compare link")
    print(f"Skipped {skipped_missing} pages referenced by database.json but missing on disk")


if __name__ == '__main__':
    main()
