"""keys.py must stay byte-compatible with the markdown slugify used for page and compare slugs."""
import json
from pathlib import Path

import pytest

from beqcatalogue.keys import compute_compare_key, slugify

ROOT = Path(__file__).resolve().parents[1]


def test_slugify_matches_markdown_for_catalogue_titles():
    toc = pytest.importorskip('markdown.extensions.toc')
    samples = ['žlutý kůň', '(500) Days of Summer', '#Alive', 'Mission: Impossible – Fallout', '  a  b\tc ']
    db = ROOT / 'docs' / 'database.json'
    if db.exists():
        samples += [e['title'] for e in json.loads(db.read_text(encoding='utf-8'))]
    for value in samples:
        assert slugify(value.casefold(), '-') == toc.slugify(value.casefold(), '-'), value
        assert slugify(value, '-') == toc.slugify(value, '-'), value


def test_compare_key_suffixes():
    assert compute_compare_key('10 Cloverfield Lane', 'film', '333371', '2016') == 'film-10-cloverfield-lane_333371'
    assert compute_compare_key('Title', 'TV', '', '2001') == 'TV-title_2001'
    assert compute_compare_key('Title', 'film') == 'film-title'
