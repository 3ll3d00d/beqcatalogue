"""Device catalogue generation: incremental, idempotent, replacement-only, revision-gated."""
import json
from pathlib import Path

import pytest

import devices

PREFIX = devices.URL_PREFIX
ROOT = Path(__file__).resolve().parents[1]


def entry(digest, title='Film', author='a1', page=None, anchor='atmos', year='2020', tmdb='1', mv='0'):
    page = page or f'{author}/{title.lower()}'
    return {'digest': digest, 'title': title, 'year': year, 'theMovieDB': tmdb, 'content_type': 'film',
            'author': author, 'catalogue_url': f'{PREFIX}{page}/#{anchor}', 'audioTypes': ['Atmos'],
            'edition': '', 'mv': mv,
            'filters': [{'type': 'LowShelf', 'freq': 20.0, 'gain': 5.0, 'q': 0.9, 'count': 2,
                         'biquads': {'96000': {'b': ['1', '-2', '1'], 'a': ['2', '-1']}}}]}


def profile(pid='float32-96k', rate=96000, revision=1, enabled=True, settings=None):
    return {'id': pid, 'label': f'label {pid}', 'description': 'd', 'rate': rate, 'storage': {'type': 'float32'},
            'transport': {'type': 'float32'}, 'settings': settings or {}, 'revision': revision, 'enabled': enabled}


@pytest.fixture
def repo(tmp_path):
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'devices' / 'profiles').mkdir(parents=True)
    return tmp_path


def write_db(root, entries):
    (root / 'docs' / 'database.json').write_text(json.dumps(entries))


def write_profile(root, p):
    (root / 'devices' / 'profiles' / f'{p["id"]}.json').write_text(json.dumps(p))


BIQUADS = [{'b': ['0.5', '0.25', '0.125'], 'a': ['1.5', '-0.5']}]


class Fake:
    """outcome per digest; records what was evaluated"""

    def __init__(self, outcomes, error=()):
        self.outcomes, self.error, self.calls = outcomes, set(error), []

    def __call__(self, task):
        d = task['digest']
        self.calls.append(d)
        if d in self.error:
            return {'digest': d, 'error': 'RuntimeError: boom'}
        o = self.outcomes.get(d, 'W')
        return {'digest': d, 'outcome': o, 'original_error_db': 1.23456, 'candidate_error_db': 0.1 if o == 'R' else None,
                'version': '0.1.0', 'biquads': BIQUADS if o == 'R' else None, 'cache_hit': o != 'N'}


def run(root, fake, pid='float32-96k', **kw):
    kw.setdefault('workers', 1)
    return devices.update(root, pid, evaluator=fake, version='0.1.0', **kw)


def catalogue(root, pid='float32-96k'):
    return json.loads((root / 'docs' / 'devices' / f'{pid}.json').read_text())


def snapshot(root):
    return {p: p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}


def test_only_replacements_are_published_and_every_outcome_is_ledgered(repo):
    write_db(repo, [entry('d1'), entry('d2'), entry('d3'), entry('d4'), entry('d5')])
    write_profile(repo, profile())
    s = run(repo, Fake({'d1': 'R', 'd2': 'W', 'd3': 'N', 'd4': 'U', 'd5': 'X'}))
    assert s['evaluated'] == 5 and s['outcomes'] == {'R': 1, 'W': 1, 'N': 1, 'U': 1, 'X': 1}
    doc = catalogue(repo)
    assert doc['entries'] == {'d1': BIQUADS}
    assert doc['profile'] == 'float32-96k' and doc['rate'] == 96000 and doc['revision'] == 1
    ledger = devices.load_ledger(repo, 'float32-96k')
    assert {d: r['outcome'] for d, r in ledger.items()} == {'d1': 'R', 'd2': 'W', 'd3': 'N', 'd4': 'U', 'd5': 'X'}
    assert ledger['d1']['original_error_db'] == '1.2346' and ledger['d1']['candidate_error_db'] == '0.1000'
    assert ledger['d2']['candidate_error_db'] == ''


def test_second_run_evaluates_nothing_and_writes_nothing(repo):
    write_db(repo, [entry('d1'), entry('d2')])
    write_profile(repo, profile())
    run(repo, Fake({'d1': 'R'}))
    before = snapshot(repo)
    fake = Fake({})
    s = run(repo, fake)
    assert fake.calls == [] and s['written'] == [] and snapshot(repo) == before


def test_only_new_digests_are_evaluated_across_several_commits(repo):
    write_profile(repo, profile())
    write_db(repo, [entry('d1')])
    run(repo, Fake({'d1': 'R'}))
    write_db(repo, [entry('d1'), entry('d2'), entry('d3')])  # two "commits" worth of additions
    fake = Fake({'d3': 'R'})
    run(repo, fake)
    assert fake.calls == ['d2', 'd3']
    assert set(catalogue(repo)['entries']) == {'d1', 'd3'}


def test_non_replacements_are_never_retried(repo):
    write_profile(repo, profile())
    write_db(repo, [entry('n'), entry('u'), entry('x')])
    run(repo, Fake({'n': 'N', 'u': 'U', 'x': 'X'}))
    fake = Fake({})
    run(repo, fake)
    assert fake.calls == []


def test_removed_and_edited_entries_are_pruned(repo):
    write_profile(repo, profile())
    write_db(repo, [entry('d1'), entry('d2')])
    run(repo, Fake({'d1': 'R', 'd2': 'R'}))
    write_db(repo, [entry('d1'), entry('d2-edited')])  # an edit changes the digest
    fake = Fake({'d2-edited': 'W'})
    s = run(repo, fake)
    assert fake.calls == ['d2-edited'] and s['pruned'] == 2
    assert set(catalogue(repo)['entries']) == {'d1'}
    assert set(devices.load_ledger(repo, 'float32-96k')) == {'d1', 'd2-edited'}


def test_unexpected_errors_are_not_recorded_and_retry(repo):
    write_profile(repo, profile())
    write_db(repo, [entry('ok'), entry('bad')])
    s = run(repo, Fake({'ok': 'R'}, error={'bad'}))
    assert s['errors'] and s['remaining'] == 1
    assert set(devices.load_ledger(repo, 'float32-96k')) == {'ok'}
    fake = Fake({'bad': 'R'})
    run(repo, fake)
    assert fake.calls == ['bad'] and set(catalogue(repo)['entries']) == {'ok', 'bad'}


def test_time_budget_leaves_remainder_pending(repo, monkeypatch):
    write_profile(repo, profile())
    write_db(repo, [entry(f'd{i}') for i in range(5)])
    clock = iter([0.0, 0.0, 0.0, 999.0, 999.0, 999.0, 999.0])
    monkeypatch.setattr(devices.time, 'monotonic', lambda: next(clock))
    s = run(repo, Fake({}), budget_minutes=1)
    assert s['evaluated'] == 2 and s['remaining'] == 3
    monkeypatch.undo()
    fake = Fake({})
    run(repo, fake)
    assert fake.calls == ['d2', 'd3', 'd4']


def test_duplicate_digests_are_evaluated_once(repo):
    write_profile(repo, profile())
    write_db(repo, [entry('d1', author='a1'), entry('d1', author='a2')])
    fake = Fake({'d1': 'R'})
    run(repo, fake)
    assert fake.calls == ['d1']


def test_output_is_deterministic_and_one_entry_per_line(repo, tmp_path_factory):
    entries = [entry(f'd{i}') for i in (3, 1, 2)]
    write_profile(repo, profile())
    write_db(repo, entries)
    run(repo, Fake({'d1': 'R', 'd2': 'R', 'd3': 'R'}))
    other = tmp_path_factory.mktemp('other')
    (other / 'docs').mkdir()
    (other / 'devices' / 'profiles').mkdir(parents=True)
    write_profile(other, profile())
    write_db(other, list(reversed(entries)))
    run(other, Fake({'d1': 'R', 'd2': 'R', 'd3': 'R'}))
    text = (repo / 'docs' / 'devices' / 'float32-96k.json').read_text()
    assert text == (other / 'docs' / 'devices' / 'float32-96k.json').read_text()
    assert [line[:5] for line in text.splitlines()[1:4]] == ['"d1":', '"d2":', '"d3":']


def test_revision_bump_reevaluates_and_drops_entries_no_longer_replaced(repo):
    write_profile(repo, profile())
    write_db(repo, [entry('d1'), entry('d2')])
    run(repo, Fake({'d1': 'R', 'd2': 'N'}))
    assert run(repo, Fake({}))['evaluated'] == 0
    write_profile(repo, profile(revision=2))
    fake = Fake({'d1': 'W', 'd2': 'R'})
    run(repo, fake)
    assert fake.calls == ['d1', 'd2']
    assert set(catalogue(repo)['entries']) == {'d2'} and catalogue(repo)['revision'] == 2


def test_config_change_without_revision_bump_is_rejected(repo):
    write_profile(repo, profile())
    write_db(repo, [entry('d1')])
    run(repo, Fake({}))
    write_profile(repo, profile(settings={'margin_db': 0.25}))
    with pytest.raises(devices.ProfileError, match='without bumping revision'):
        run(repo, Fake({}))
    with pytest.raises(devices.ProfileError):
        devices.matrix(repo)
    write_profile(repo, profile(settings={'margin_db': 0.25}, revision=2))
    assert run(repo, Fake({}))['evaluated'] == 1


@pytest.mark.parametrize('bad', [
    {'rate': 44100}, {'storage': {'type': 'fixed5.23'}}, {'settings': {'nope': 1}}, {'revision': 0},
    {'enabled': 'yes'}, {'id': 'other'}, {'label': ''},
])
def test_invalid_profiles_are_rejected(repo, bad):
    write_profile(repo, profile())
    (repo / 'devices' / 'profiles' / 'float32-96k.json').write_text(json.dumps({**profile(), **bad}))
    with pytest.raises(devices.ProfileError):
        devices.load_profile(repo, 'float32-96k')


def test_matrix(repo, capsys):
    write_db(repo, [entry('d1'), entry('d2')])
    assert devices.matrix(repo) == {'include': []}
    devices.main(['--root', str(repo), 'matrix'])
    assert capsys.readouterr().out.splitlines() == ['matrix={"include":[]}', 'has_work=false']
    write_profile(repo, profile())
    write_profile(repo, profile('float32-48k', rate=48000))
    write_profile(repo, profile('off', enabled=False))
    assert devices.matrix(repo) == {'include': [{'profile': 'float32-48k', 'pending': 2},
                                                {'profile': 'float32-96k', 'pending': 2}]}
    run(repo, Fake({}))
    assert devices.matrix(repo) == {'include': [{'profile': 'float32-48k', 'pending': 2}]}
    write_db(repo, [entry('d1')])  # pruning alone is work too
    assert devices.matrix(repo)['include'][1] == {'profile': 'float32-96k', 'pending': 1}


def test_site_data(repo):
    write_profile(repo, profile())
    write_profile(repo, profile('float32-48k', rate=48000))
    write_db(repo, [
        entry('d1', title='Film', author='a1', anchor='atmos'),
        entry('d1', title='Film', author='a2', anchor='atmos'),
        entry('d2', title='Film', author='a1', anchor='dts-hd-ma-51'),
        entry('d3', title='Other', author='a1'),
    ])
    run(repo, Fake({'d1': 'R', 'd2': 'R'}))
    run(repo, Fake({'d1': 'R'}), pid='float32-48k')
    devices.site(repo)
    out = repo / 'docs' / 'devices'
    assert sorted(p.name for p in (out / 'compare').iterdir()) == ['film-film_1.json']
    per_title = json.loads((out / 'compare' / 'film-film_1.json').read_text())
    assert [(e['author'], e['digest'], sorted(e['profiles'])) for e in per_title] == [
        ('a1', 'd1', ['float32-48k', 'float32-96k']), ('a1', 'd2', ['float32-96k']),
        ('a2', 'd1', ['float32-48k', 'float32-96k'])]
    assert per_title[0]['profiles']['float32-96k'] == {'after': BIQUADS, 'before_db': 1.2346, 'after_db': 0.1}
    assert per_title[0]['filters'][0]['biquads']['96000']['b'] == ['1', '-2', '1']
    shards = sorted(p.name for p in (out / 'pages').iterdir())
    assert len(shards) == 256 and shards[0] == '00.json' and shards[-1] == 'ff.json'
    page = 'a1/film/'
    shard = json.loads((out / 'pages' / f'{devices.fnv1a_bucket(page)}.json').read_text())
    assert shard[page] == [
        {'anchor': 'atmos', 'digest': 'd1', 'key': 'film-film_1', 'profiles': ['label float32-48k', 'label float32-96k']},
        {'anchor': 'dts-hd-ma-51', 'digest': 'd2', 'key': 'film-film_1', 'profiles': ['label float32-96k']}]
    pages = {}
    for p in (out / 'pages').iterdir():
        pages.update(json.loads(p.read_text()))
    assert sorted(pages) == ['a1/film/', 'a2/film/']
    assert json.loads((out / 'titles.json').read_text()) == [
        {'key': 'film-film_1', 'title': 'Film', 'year': '2020', 'content_type': 'film', 'authors': ['a1', 'a2']}]
    index = json.loads((out / 'index.json').read_text())
    assert [(p['id'], p['entries']) for p in index['profiles']] == [('float32-48k', 1), ('float32-96k', 2)]

    before = snapshot(repo)
    assert devices.site(repo)['written'] == 0 and snapshot(repo) == before

    write_db(repo, [entry('d3', title='Other', author='a1')])  # Film removed entirely
    run(repo, Fake({}))
    run(repo, Fake({}), pid='float32-48k')
    assert devices.site(repo)['removed'] == 1
    assert not list((out / 'compare').iterdir())
    assert len(list((out / 'pages').iterdir())) == 256


def test_fnv1a_bucket_fixture():
    # shared with tests/js/devices-flag.test.mjs so Python and JS agree on shards
    fixture = json.loads((ROOT / 'tests' / 'fixtures' / 'fnv1a.json').read_text())
    for value, bucket in fixture.items():
        assert devices.fnv1a_bucket(value) == bucket, value


def test_real_optimiser_on_a_tiny_catalogue(repo):
    pytest.importorskip('beqoptimiser')
    sharp = {'digest': 'sharp', 'title': 'Sharp', 'mv': '0', 'catalogue_url': '',
             'filters': [{'type': 'PeakingEQ', 'freq': 10.0, 'gain': 12.0, 'q': 0.7, 'count': 1}]}
    mild = {'digest': 'mild', 'title': 'Mild', 'mv': '0', 'catalogue_url': '',
            'filters': [{'type': 'LowShelf', 'freq': 120.0, 'gain': 1.0, 'q': 0.7, 'count': 1}]}
    write_db(repo, [sharp, mild, {'digest': 'none', 'title': 'None', 'filters': []}])
    for p in (profile(), profile('float32-48k', rate=48000)):
        write_profile(repo, p)
        s = devices.update(repo, p['id'], workers=1, use_cache=False)
        assert s['evaluated'] == 3 and not s['errors']
        ledger = devices.load_ledger(repo, p['id'])
        assert ledger['mild']['outcome'] == 'W' and ledger['none']['outcome'] == 'X'
        published = catalogue(repo, p['id'])['entries']
        assert set(published) <= {'sharp'}
        for rows in published.values():
            assert all(len(r['b']) == 3 and len(r['a']) == 2 for r in rows)
    assert devices.load_ledger(repo, 'float32-96k')['sharp']['outcome'] == 'R'
