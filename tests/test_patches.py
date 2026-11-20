"""meta/entry_patches.json must stay applicable, and applying must be safe to repeat."""
import copy
import json
from pathlib import Path

from beqcatalogue.patches import DEFAULT_PATCH_FILE, apply_entry_patches, load_patches

ROOT = Path(__file__).resolve().parents[1]


def entry(**kw):
    base = {'author': 'mobe1969', 'underlying': 'X (2020) DTS-HD MA 5.1', 'title': 'X', 'sortTitle': 'x',
            'content_type': 'film', 'theMovieDB': '1', 'digest': 'abc'}
    return {**base, **kw}


def patch(**kw):
    base = {'author': 'mobe1969', 'underlying': 'X (2020) DTS-HD MA 5.1', 'set': {'title': 'Y'},
            'expect': {'title': 'X'}}
    return {**base, **kw}


def test_applies_then_is_idempotent():
    entries = [entry()]
    r1 = apply_entry_patches(entries, [patch()])
    assert len(r1.applied) == 1 and entries[0]['title'] == 'Y'
    assert entries[0]['sortTitle'] == 'y'
    assert entries[0]['digest'] == 'abc'
    r2 = apply_entry_patches(entries, [patch()])
    assert not r2.applied and len(r2.already) == 1


def test_drifted_value_is_reported_not_overwritten():
    entries = [entry(title='Z')]
    r = apply_entry_patches(entries, [patch()])
    assert len(r.conflicts) == 1 and entries[0]['title'] == 'Z'


def test_absent_field_matches_blank_expectation_and_is_added():
    entries = [entry()]
    r = apply_entry_patches(entries, [patch(set={'content_type': 'TV', 'season': '1', 'episode': ''},
                                            expect={'content_type': 'film', 'season': ''})])
    assert len(r.applied) == 1
    assert entries[0]['season'] == '1' and entries[0]['episode'] == ''


def test_other_authors_and_unknown_entries_untouched():
    entries = [entry(author='kaelaria')]
    before = copy.deepcopy(entries)
    r = apply_entry_patches(entries, [patch()])
    assert entries == before and len(r.unmatched) == 1


def test_committed_patches_are_valid_and_fully_applied():
    patches = load_patches(DEFAULT_PATCH_FILE)
    assert patches
    assert len({(p['author'], p['underlying']) for p in patches}) == len(patches)
    db = ROOT / 'docs' / 'database.json'
    entries = json.loads(db.read_text(encoding='utf-8'))
    r = apply_entry_patches(entries, patches)
    assert not r.conflicts and not r.unmatched and not r.applied, r.summary()
