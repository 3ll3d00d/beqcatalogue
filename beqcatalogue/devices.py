'''Device-specific optimised catalogues, one per committed format profile.

Run as a script, like the main build (it must not import the site dependencies):

    python beqcatalogue/devices.py matrix                  # GitHub matrix of profiles with work
    python beqcatalogue/devices.py update --profile ID     # evaluate new digests for one profile
    python beqcatalogue/devices.py site                    # derived website data for all profiles
    python beqcatalogue/devices.py bootstrap               # unbudgeted update of every profile + site

Per profile ``devices/profiles/<id>.json`` drives two files:

* ``docs/devices/<id>.json``, the published device catalogue: main catalogue digest -> optimised
  biquads, holding *only* entries the optimiser replaced.
* ``meta/devices/<id>.tsv``, the evaluation ledger: every evaluated digest whatever its outcome, so
  nothing is re-optimised until the profile's ``revision`` is bumped.

Every run is a pure function of docs/database.json, the ledger and the profile, so reruns converge
on the same bytes and write nothing when there is nothing new. Only ``update``/``bootstrap`` import
beqoptimiser (the optional ``optimiser`` dependency group); everything else is stdlib only.
'''
import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from keys import compute_compare_key  # noqa: E402

PROFILE_DIR = Path('devices/profiles')
CATALOGUE_DIR = Path('docs/devices')
LEDGER_DIR = Path('meta/devices')
DB_PATH = Path('docs/database.json')
URL_PREFIX = 'https://beqcatalogue.readthedocs.io/en/latest/'
SCHEMA_VERSION = 1
LOADING_MODEL = 'additive-feedback-decimal17-v1'
SHARDS = 256

OUTCOME_CODES = {'replacement': 'R', 'within_margin': 'W', 'no_replacement': 'N', 'unresolved': 'U',
                 'unsupported': 'X'}
PRECISION_TYPES = ('float32',)  # optimise_entry is float32-only until beqforge exposes precision
SETTINGS_KEYS = ('margin_db', 'band_hz', 'guard_margin_db', 'numerical_tolerance_db', 'passes', 'grid_points',
                 'validation_points')
# the exceptions beqoptimiser's own CLI reports as an unsupported entry rather than a failure
UNSUPPORTED_ERRORS = (ValueError, KeyError, TypeError, OverflowError)


class ProfileError(ValueError):
    pass


# ---------------------------------------------------------------------------------------------
# profiles

def load_profiles(root: Path, enabled_only: bool = True) -> list[dict]:
    profiles = []
    for path in sorted((root / PROFILE_DIR).glob('*.json')):
        profile = json.loads(path.read_text(encoding='utf-8'))
        validate_profile(profile, path.stem)
        if profile['enabled'] or not enabled_only:
            profiles.append(profile)
    return profiles


def load_profile(root: Path, profile_id: str) -> dict:
    path = root / PROFILE_DIR / f'{profile_id}.json'
    if not path.exists():
        raise ProfileError(f'no profile config at {path}')
    profile = json.loads(path.read_text(encoding='utf-8'))
    validate_profile(profile, profile_id)
    return profile


def validate_profile(profile: dict, stem: str):
    def fail(msg):
        raise ProfileError(f'profile {stem}: {msg}')

    if not isinstance(profile, dict):
        fail('must be a JSON object')
    if profile.get('id') != stem or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', stem):
        fail('id must match the file name and be lower-case kebab case')
    for key in ('label', 'description'):
        if not isinstance(profile.get(key), str) or not profile[key]:
            fail(f'{key} must be a non-empty string')
    if profile.get('rate') not in (48000, 96000):
        fail('rate must be 48000 or 96000')
    for key in ('storage', 'transport'):
        spec = profile.get(key)
        if not isinstance(spec, dict) or spec.get('type') not in PRECISION_TYPES or set(spec) != {'type'}:
            fail(f'{key} must be one of {[{"type": t} for t in PRECISION_TYPES]}')
    settings = profile.get('settings', None)
    if not isinstance(settings, dict) or any(k not in SETTINGS_KEYS for k in settings):
        fail(f'settings must be an object with keys from {SETTINGS_KEYS}')
    revision = profile.get('revision')
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        fail('revision must be a positive integer')
    if not isinstance(profile.get('enabled'), bool):
        fail('enabled must be true or false')


def config_digest(profile: dict) -> str:
    ''' identifies everything that changes optimiser output; a change requires a revision bump '''
    numerical = {k: profile[k] for k in ('rate', 'storage', 'transport', 'settings')}
    return hashlib.sha256(json.dumps(numerical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def check_revision(profile: dict, header: dict | None, ledger: dict):
    ''' a numerical config change is only allowed alongside a revision bump, and never backwards '''
    pid, revision = profile['id'], profile['revision']
    if header is not None:
        if revision < header['revision']:
            raise ProfileError(f'profile {pid}: revision {revision} is lower than published {header["revision"]}')
        if revision == header['revision'] and header['config_digest'] != config_digest(profile):
            raise ProfileError(f'profile {pid}: numerical config changed without bumping revision '
                               f'(published revision {header["revision"]})')
    newest = max((row['revision'] for row in ledger.values()), default=0)
    if newest > revision:
        raise ProfileError(f'profile {pid}: ledger holds revision {newest}, newer than config revision {revision}')


# ---------------------------------------------------------------------------------------------
# files

def catalogue_path(root: Path, pid: str) -> Path:
    return root / CATALOGUE_DIR / f'{pid}.json'


def ledger_path(root: Path, pid: str) -> Path:
    return root / LEDGER_DIR / f'{pid}.tsv'


def load_device_catalogue(root: Path, pid: str) -> tuple[dict | None, dict]:
    path = catalogue_path(root, pid)
    if not path.exists():
        return None, {}
    document = json.loads(path.read_text(encoding='utf-8'))
    entries = document.pop('entries')
    return document, entries


def render_device_catalogue(profile: dict, entries: dict) -> str:
    header = {
        'schema_version': SCHEMA_VERSION,
        'profile': profile['id'],
        'revision': profile['revision'],
        'config_digest': config_digest(profile),
        'rate': profile['rate'],
        'storage': profile['storage']['type'],
        'transport': profile['transport']['type'],
        'loading_model': LOADING_MODEL,
    }
    head = json.dumps(header, sort_keys=True, separators=(',', ':'))[:-1]
    # one entry per line keeps git diffs proportional to what changed
    lines = [f'{json.dumps(d)}:{json.dumps(entries[d], separators=(",", ":"))}' for d in sorted(entries)]
    return head + ',"entries":{\n' + ',\n'.join(lines) + ('\n' if lines else '') + '}}\n'


def format_db(value) -> str:
    if value is None or not isinstance(value, (int, float)) or value != value or value in (float('inf'), float('-inf')):
        return ''
    return f'{value:.4f}'


def load_ledger(root: Path, pid: str) -> dict:
    path = ledger_path(root, pid)
    ledger = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line or line.startswith('#'):
                continue
            digest, outcome, revision, original, candidate, version = line.split('\t')
            ledger[digest] = {'outcome': outcome, 'revision': int(revision), 'original_error_db': original,
                              'candidate_error_db': candidate, 'version': version}
    return ledger


def render_ledger(ledger: dict) -> str:
    rows = ['#digest\toutcome\trevision\toriginal_error_db\tcandidate_error_db\tversion']
    for digest in sorted(ledger):
        r = ledger[digest]
        rows.append('\t'.join([digest, r['outcome'], str(r['revision']), r['original_error_db'],
                               r['candidate_error_db'], r['version']]))
    return '\n'.join(rows) + '\n'


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding='utf-8') == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(content, encoding='utf-8')
    tmp.replace(path)
    return True


def load_catalogue(root: Path) -> list[dict]:
    with open(root / DB_PATH, encoding='utf-8') as f:
        return json.load(f)


def entries_by_digest(catalogue: list[dict]) -> dict:
    ''' duplicate digests share title, filters and offset, so the first entry stands for all '''
    by_digest = {}
    for entry in catalogue:
        digest = entry.get('digest')
        if digest and digest not in by_digest:
            by_digest[digest] = entry
    return by_digest


def pending_digests(profile: dict, digests, ledger: dict) -> list[str]:
    return sorted(d for d in digests if d not in ledger or ledger[d]['revision'] < profile['revision'])


# ---------------------------------------------------------------------------------------------
# evaluation

def evaluate(task: dict) -> dict:
    ''' optimise one catalogue entry for one profile; runs in a worker process '''
    from beqoptimiser import Settings
    from beqoptimiser.cache import ResultCache
    from beqoptimiser.cli import optimise_entry

    class CountingCache(ResultCache):
        hit = False

        def get(self, request):
            result = super().get(request)
            self.hit = result is not None
            return result

    digest = task['digest']
    settings = dict(task['settings'])
    if 'band_hz' in settings:
        settings['band_hz'] = tuple(settings['band_hz'])
    cache = CountingCache(task['cache_dir']) if task['use_cache'] else False
    try:
        report = optimise_entry(task['entry'], rate=task['rate'], settings=Settings(**settings), cache=cache)
    except UNSUPPORTED_ERRORS as e:
        return {'digest': digest, 'outcome': 'X', 'original_error_db': None, 'candidate_error_db': None,
                'version': task['version'], 'biquads': None, 'cache_hit': False, 'reason': str(e)}
    except Exception as e:  # recorded nowhere, so it is retried next run without blocking the rest
        return {'digest': digest, 'error': f'{type(e).__name__}: {e}'}
    result = report['result']
    variant = report['variant']
    return {
        'digest': digest,
        'outcome': OUTCOME_CODES[result['outcome']],
        'original_error_db': result.get('original_error_db'),
        'candidate_error_db': result.get('candidate_error_db'),
        'version': result.get('version') or task['version'],
        'biquads': variant['biquads'] if variant else None,
        'cache_hit': bool(cache and cache.hit),
    }


def run_tasks(tasks: list[dict], evaluator, workers: int, deadline: float | None) -> tuple[list[dict], int]:
    ''' returns (results, number not attempted because the time budget ran out) '''
    results = []
    if workers <= 1:
        for i, task in enumerate(tasks):
            if deadline is not None and time.monotonic() >= deadline:
                return results, len(tasks) - i
            results.append(evaluator(task))
        return results, 0
    executor = ProcessPoolExecutor(max_workers=workers)
    try:
        futures = {executor.submit(evaluator, t): t['digest'] for t in tasks}
        remaining = set(futures)
        while remaining:
            timeout = None if deadline is None else max(0.0, deadline - time.monotonic())
            done, remaining = wait(remaining, timeout=timeout, return_when=FIRST_COMPLETED)
            for f in done:
                results.append(_future_result(f, futures[f]))
            if deadline is not None and time.monotonic() >= deadline:
                break
        # stop handing out work; in-flight tasks finish and are kept
        executor.shutdown(wait=True, cancel_futures=True)
        skipped = 0
        for f in remaining:
            if f.cancelled():
                skipped += 1
            else:
                results.append(_future_result(f, futures[f]))
        return results, skipped
    finally:
        executor.shutdown(wait=True, cancel_futures=True)


def _future_result(future, digest: str) -> dict:
    try:
        return future.result()
    except Exception as e:
        return {'digest': digest, 'error': f'{type(e).__name__}: {e}'}


def optimiser_version() -> str:
    from beqoptimiser import __version__
    return __version__


def update(root: Path, profile_id: str, budget_minutes: float | None = 45, workers: int = 4,
           cache_dir: str | None = None, use_cache: bool = True, evaluator=None, version: str | None = None) -> dict:
    profile = load_profile(root, profile_id)
    header, device_entries = load_device_catalogue(root, profile_id)
    ledger = load_ledger(root, profile_id)
    check_revision(profile, header, ledger)

    by_digest = entries_by_digest(load_catalogue(root))
    live = set(by_digest)
    pruned = len(set(ledger) - live) + len(set(device_entries) - live)
    ledger = {d: r for d, r in ledger.items() if d in live}
    device_entries = {d: b for d, b in device_entries.items() if d in live}

    pending = pending_digests(profile, live, ledger)
    summary = {'profile': profile_id, 'label': profile['label'], 'pending': len(pending), 'pruned': pruned,
               'evaluated': 0, 'cache_hits': 0, 'computed': 0, 'remaining': 0, 'errors': [],
               'outcomes': {c: 0 for c in OUTCOME_CODES.values()}, 'changes': []}
    if pending:
        evaluator = evaluator or evaluate
        version = version or optimiser_version()
        tasks = [{'digest': d, 'entry': by_digest[d], 'rate': profile['rate'], 'settings': profile['settings'],
                  'cache_dir': cache_dir, 'use_cache': use_cache, 'version': version} for d in pending]
        deadline = None if not budget_minutes else time.monotonic() + budget_minutes * 60
        results, summary['remaining'] = run_tasks(tasks, evaluator, workers, deadline)
        for r in sorted(results, key=lambda x: x['digest']):
            digest = r['digest']
            if 'error' in r:
                summary['errors'].append(f'{digest}: {r["error"]}')
                continue
            summary['evaluated'] += 1
            summary['outcomes'][r['outcome']] += 1
            summary['cache_hits' if r['cache_hit'] else 'computed'] += 1
            ledger[digest] = {'outcome': r['outcome'], 'revision': profile['revision'],
                              'original_error_db': format_db(r['original_error_db']),
                              'candidate_error_db': format_db(r['candidate_error_db']), 'version': r['version']}
            entry = by_digest[digest]
            summary['changes'].append({
                'digest': digest, 'title': entry.get('title', ''), 'year': entry.get('year', ''),
                'author': entry.get('author', ''), 'audioTypes': entry.get('audioTypes', []),
                'outcome': r['outcome'], 'original_error_db': ledger[digest]['original_error_db'],
                'candidate_error_db': ledger[digest]['candidate_error_db'],
                'was_published': digest in device_entries,
            })
            if r['outcome'] == 'R':
                device_entries[digest] = r['biquads']
            else:
                device_entries.pop(digest, None)
        summary['remaining'] += len(summary['errors'])

    summary['catalogue_entries'] = len(device_entries)
    summary['written'] = [str(p.relative_to(root)) for p, content in (
        (catalogue_path(root, profile_id), render_device_catalogue(profile, device_entries)),
        (ledger_path(root, profile_id), render_ledger(ledger)),
    ) if write_if_changed(p, content)]
    return summary


# ---------------------------------------------------------------------------------------------
# matrix

def profile_work(root: Path, profile: dict, live: set) -> int:
    header, device_entries = load_device_catalogue(root, profile['id'])
    ledger = load_ledger(root, profile['id'])
    check_revision(profile, header, ledger)
    stale = (set(ledger) - live) | (set(device_entries) - live)
    work = len(pending_digests(profile, live, ledger)) + len(stale)
    if header is None or header['revision'] != profile['revision']:
        work = max(work, 1)  # a new or re-revisioned profile always rewrites its header
    return work


def matrix(root: Path) -> dict:
    live = set(entries_by_digest(load_catalogue(root)))
    include = []
    for profile in load_profiles(root):
        work = profile_work(root, profile, live)
        if work:
            include.append({'profile': profile['id'], 'pending': work})
    return {'include': include}


# ---------------------------------------------------------------------------------------------
# site

def fnv1a_bucket(value: str) -> str:
    ''' must match bucketOf() in docs/javascripts/devices-flag.js '''
    h = 0x811c9dc5
    for b in value.encode('utf-8'):
        h = ((h ^ b) * 0x01000193) & 0xffffffff
    return f'{h % SHARDS:02x}'


def split_catalogue_url(url: str) -> tuple[str, str] | None:
    if not url or not url.startswith(URL_PREFIX):
        return None
    page, _, anchor = url[len(URL_PREFIX):].partition('#')
    if not page.endswith('/'):
        page += '/'
    return page, anchor


def site(root: Path) -> dict:
    catalogue = load_catalogue(root)
    profiles = load_profiles(root)
    out = root / CATALOGUE_DIR
    optimised = {}  # profile id -> {digest: biquads}
    ledgers = {}
    index_profiles = []
    for profile in profiles:
        pid = profile['id']
        _, entries = load_device_catalogue(root, pid)
        optimised[pid] = entries
        ledgers[pid] = load_ledger(root, pid)
        path = catalogue_path(root, pid)
        index_profiles.append({
            'id': pid, 'label': profile['label'], 'description': profile['description'], 'rate': profile['rate'],
            'storage': profile['storage']['type'], 'transport': profile['transport']['type'],
            'revision': profile['revision'], 'file': f'{pid}.json', 'entries': len(entries),
            'margin_db': profile['settings'].get('margin_db', 0.5),
            'band_hz': profile['settings'].get('band_hz', [2.0, 200.0]),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
        })

    titles = {}
    per_key = {}
    shards = {f'{i:02x}': {} for i in range(SHARDS)}
    for entry in catalogue:
        digest = entry.get('digest')
        if not digest or not entry.get('title') or not entry.get('filters'):
            continue
        hits = [p for p in profiles if digest in optimised[p['id']]]
        if not hits:
            continue
        key = compute_compare_key(entry['title'], entry.get('content_type', ''), entry.get('theMovieDB', ''),
                                  entry.get('year', ''))
        per_key.setdefault(key, []).append({
            'digest': digest,
            'author': entry.get('author', ''),
            'catalogue_url': entry.get('catalogue_url', ''),
            'audioTypes': entry.get('audioTypes', []),
            'edition': entry.get('edition', ''),
            'season': entry.get('season', ''),
            'episode': entry.get('episode', ''),
            'mv': entry.get('mv', '0'),
            'filters': [{k: f[k] for k in ('type', 'freq', 'gain', 'q', 'count', 'biquads') if k in f}
                        for f in entry['filters']],
            'profiles': {p['id']: {
                'after': optimised[p['id']][digest],
                'before_db': _float(ledgers[p['id']].get(digest, {}).get('original_error_db')),
                'after_db': _float(ledgers[p['id']].get(digest, {}).get('candidate_error_db')),
            } for p in hits},
        })
        title = titles.setdefault(key, {'key': key, 'title': entry['title'], 'year': entry.get('year', ''),
                                        'content_type': entry.get('content_type', ''), 'authors': set()})
        title['authors'].add(entry.get('author', ''))
        location = split_catalogue_url(entry.get('catalogue_url', ''))
        if location:
            page, anchor = location
            items = shards[fnv1a_bucket(page)].setdefault(page, [])
            item = {'anchor': anchor, 'digest': digest, 'key': key, 'profiles': [p['label'] for p in hits]}
            if item not in items:
                items.append(item)

    written = []
    compact = {'separators': (',', ':'), 'sort_keys': True}
    for key, entries in per_key.items():
        entries.sort(key=lambda e: (e['author'], e['catalogue_url'], e['digest']))
        if write_if_changed(out / 'compare' / f'{key}.json', json.dumps(entries, **compact) + '\n'):
            written.append(f'compare/{key}.json')
    removed = 0
    if (out / 'compare').exists():
        for existing in (out / 'compare').glob('*.json'):
            if existing.stem not in per_key:
                existing.unlink()
                removed += 1
    for bucket, pages in shards.items():
        for items in pages.values():
            items.sort(key=lambda i: (i['anchor'], i['digest']))
        if write_if_changed(out / 'pages' / f'{bucket}.json', json.dumps(pages, **compact) + '\n'):
            written.append(f'pages/{bucket}.json')
    title_list = sorted(({**t, 'authors': sorted(t['authors'])} for t in titles.values()),
                        key=lambda t: (t['title'].casefold(), t['key']))
    if write_if_changed(out / 'titles.json', json.dumps(title_list, **compact) + '\n'):
        written.append('titles.json')
    index = {'schema_version': SCHEMA_VERSION, 'profiles': index_profiles}
    if write_if_changed(out / 'index.json', json.dumps(index, indent=1, sort_keys=True) + '\n'):
        written.append('index.json')
    return {'titles': len(per_key), 'written': len(written), 'removed': removed}


def _float(value):
    return float(value) if value not in (None, '') else None


# ---------------------------------------------------------------------------------------------
# bootstrap

def seed_compatible() -> tuple[bool, dict]:
    ''' whether beqforge's bundled result seed matches this environment's implementation identity '''
    from beqoptimiser import cache
    return bool(cache._bundled_entries()), cache.implementation_identity()


def bootstrap(root: Path, workers: int, cache_dir: str | None, use_cache: bool, allow_cold: bool) -> list[dict]:
    compatible, identity = seed_compatible()
    print(f'Optimiser implementation identity: {json.dumps(identity, sort_keys=True)}')
    if not compatible:
        message = 'bundled optimiser seed is not compatible with this environment; every miss computes cold'
        if not allow_cold:
            raise SystemExit(f'{message}. Rerun with --allow-cold to proceed anyway.')
        print(f'WARNING: {message}')
    else:
        print('Bundled optimiser seed is compatible')
    summaries = []
    for profile in load_profiles(root):
        print(f'Bootstrapping {profile["id"]}...', flush=True)
        summary = update(root, profile['id'], budget_minutes=None, workers=workers, cache_dir=cache_dir,
                         use_cache=use_cache)
        report(summary)
        summaries.append(summary)
    print(f'Site: {site(root)}')
    return summaries


# ---------------------------------------------------------------------------------------------
# cli

OUTCOME_NAMES = {'R': 'replacement', 'W': 'within margin', 'N': 'no replacement', 'U': 'unresolved',
                 'X': 'unsupported'}


def render_summary(summary: dict, max_changes: int = 100) -> str:
    ''' markdown describing what one profile update did, for GitHub step/run summaries '''
    o = summary['outcomes']
    lines = [
        f"### Device catalogue `{summary['profile']}`",
        '',
        '| pending | evaluated | cache hits | computed | remaining | pruned | catalogue entries |',
        '|-|-|-|-|-|-|-|',
        f"| {summary['pending']} | {summary['evaluated']} | {summary['cache_hits']} | {summary['computed']} | "
        f"{summary['remaining']} | {summary['pruned']} | {summary['catalogue_entries']} |",
        '',
        'Outcomes: ' + ', '.join(f'{OUTCOME_NAMES[c]} {o[c]}' for c in OUTCOME_NAMES),
        '',
        f"Written: {', '.join(summary['written']) or 'nothing (unchanged)'}",
    ]
    changes = summary.get('changes', [])
    if changes:
        # replacements first, as they are what gets published
        ordered = sorted(changes, key=lambda c: (c['outcome'] != 'R', c['title'].casefold(), c['digest']))
        lines += ['', '| title | author | format | outcome | max error before → optimised (dB) | published |',
                  '|-|-|-|-|-|-|']
        for c in ordered[:max_changes]:
            title = f"{c['title']} ({c['year']})" if c['year'] else c['title']
            after = f" → {c['candidate_error_db']}" if c['outcome'] == 'R' else ''
            if c['outcome'] == 'R':
                published = 'updated' if c['was_published'] else 'added'
            else:
                published = 'removed' if c['was_published'] else '–'
            lines.append(f"| {title} | {c['author']} | {', '.join(c['audioTypes'])} | {OUTCOME_NAMES[c['outcome']]} | "
                         f"{c['original_error_db'] or '–'}{after} | {published} |")
        if len(ordered) > max_changes:
            lines += ['', f'…and {len(ordered) - max_changes} more']
    if summary['errors']:
        lines += ['', f"{len(summary['errors'])} unexpected error(s), will retry next run:", '']
        lines += [f'* `{e}`' for e in summary['errors'][:50]]
    return '\n'.join(lines) + '\n'


def commit_line(summary: dict) -> str:
    o = summary['outcomes']
    parts = [f"{summary['evaluated']} evaluated"]
    parts += [f'{o[c]} {OUTCOME_NAMES[c]}' for c in OUTCOME_NAMES if o[c]]
    added = sum(1 for c in summary.get('changes', []) if c['outcome'] == 'R' and not c['was_published'])
    removed = sum(1 for c in summary.get('changes', []) if c['outcome'] != 'R' and c['was_published'])
    parts.append(f'{added} added, {removed} removed, {summary["catalogue_entries"]} published')
    if summary['pruned']:
        parts.append(f"{summary['pruned']} pruned")
    if summary['remaining']:
        parts.append(f"{summary['remaining']} remaining")
    return f"{summary['profile']}: " + ', '.join(parts)


def report(summary: dict, summary_file: str | None = None):
    text = render_summary(summary)
    print(text, flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
            f.write(text)
    if summary_file:
        Path(summary_file).parent.mkdir(parents=True, exist_ok=True)
        Path(summary_file).write_text(json.dumps(summary, indent=1), encoding='utf-8')


def summarise(files: list[str], commit_message: bool = False) -> str:
    ''' combines per-profile update summaries (from --summary-file) for the publish job '''
    summaries = sorted((json.loads(Path(f).read_text(encoding='utf-8')) for f in files),
                       key=lambda s: s['profile'])
    if commit_message:
        return '\n'.join(['Updated device catalogues', ''] + [commit_line(s) for s in summaries]) + '\n'
    if not summaries:
        return '## Device catalogues\n\nNo profile had new digests to evaluate.\n'
    return '## Device catalogues\n\n' + '\n'.join(render_summary(s) for s in summaries)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--root', type=Path, default=Path('.'), help='repository root (default: cwd)')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('matrix', help='print GitHub outputs: matrix=<json> and has_work=<bool>')
    for name in ('update', 'bootstrap'):
        p = sub.add_parser(name)
        if name == 'update':
            p.add_argument('--profile', required=True)
            p.add_argument('--budget-minutes', type=float, default=45, help='0 = unlimited')
        else:
            p.add_argument('--allow-cold', action='store_true',
                           help='proceed even if the bundled optimiser seed does not match this environment')
        p.add_argument('--workers', type=int, default=min(4, os.cpu_count() or 1))
        p.add_argument('--cache-dir', help='optimiser result cache (default: BEQOPTIMISER_CACHE_DIR or '
                                           '~/.cache/beqoptimiser)')
        p.add_argument('--no-cache', action='store_true')
        if name == 'update':
            p.add_argument('--summary-file', help='also write the run summary as JSON, for `summarise`')
    sub.add_parser('site', help='write the derived website data under docs/devices')
    p = sub.add_parser('summarise', help='combine update --summary-file outputs into markdown or a commit message')
    p.add_argument('files', nargs='*')
    p.add_argument('--commit-message', action='store_true')
    args = parser.parse_args(argv)
    root = args.root
    try:
        if args.command == 'matrix':
            m = matrix(root)
            print(f'matrix={json.dumps(m, separators=(",", ":"))}')
            print(f'has_work={"true" if m["include"] else "false"}')
            if os.environ.get('GITHUB_STEP_SUMMARY'):
                rows = [f"| `{i['profile']}` | {i['pending']} |" for i in m['include']]
                text = ('## Device profiles with work\n\n| profile | digests to evaluate or prune |\n|-|-|\n'
                        + '\n'.join(rows) + '\n') if rows else '## Device profiles\n\nNo profile has new work.\n'
                with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
                    f.write(text)
        elif args.command == 'update':
            summary = update(root, args.profile, budget_minutes=args.budget_minutes or None, workers=args.workers,
                             cache_dir=args.cache_dir, use_cache=not args.no_cache)
            report(summary, args.summary_file)
        elif args.command == 'bootstrap':
            bootstrap(root, args.workers, args.cache_dir, not args.no_cache, args.allow_cold)
        elif args.command == 'site':
            result = site(root)
            print(f'Site: {result}')
            if os.environ.get('GITHUB_STEP_SUMMARY'):
                with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
                    f.write(f"\n### Device site data\n\n{result['titles']} optimised titles; {result['written']} "
                            f"file(s) written, {result['removed']} removed\n")
        elif args.command == 'summarise':
            sys.stdout.write(summarise(args.files, args.commit_message))
    except ProfileError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
