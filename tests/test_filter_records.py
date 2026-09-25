"""The configured version-1 JSON source must reach the public database."""
import csv
import json
import os
import subprocess
from collections import defaultdict
from pathlib import Path

import beqcatalogue


ROOT = Path(__file__).resolve().parents[1]


def test_configured_source_record_is_processed_and_finalised(tmp_path, monkeypatch):
    assert beqcatalogue.RECORD_REPO_CONFIGS == [('3ll3d00d', '.input/3ll3d00d/beqfilters')]
    author, relative_path = beqcatalogue.RECORD_REPO_CONFIGS[0]
    source = tmp_path / relative_path
    (source / 'movies').mkdir(parents=True)
    record = {
        'title': 'Fixture Film', 'year': '2024', 'audioTypes': ['DTS-HD.MA 5.1'],
        'content_type': 'film', 'author': author, 'filters': [], 'mv': '0',
        'created_at': 100, 'updated_at': 100,
    }
    record['digest'] = beqcatalogue.digest(record)
    (source / 'movies' / 'fixture.json').write_text(json.dumps(record), encoding='utf-8')
    (source / 'database.json').write_text(json.dumps([record]), encoding='utf-8')
    (tmp_path / 'docs').mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(beqcatalogue, 'error_files', defaultdict(list), raising=False)
    monkeypatch.setattr(beqcatalogue, 'source_record_times', {})
    monkeypatch.setattr(beqcatalogue, 'json_catalogue', [], raising=False)
    monkeypatch.setattr(beqcatalogue, 'times', {author: {}}, raising=False)
    with (tmp_path / 'database.csv').open('w', newline='') as handle:
        monkeypatch.setattr(beqcatalogue, 'db_writer', csv.writer(handle), raising=False)
        extracted = beqcatalogue.extract_filter_records(relative_path, author)
        assert len(extracted) == 1  # the aggregate is derived, not another title
        beqcatalogue.process_content_from_repo(author, extracted, [], 'film', [])
    assert beqcatalogue.error_files[author] == []
    assert len(beqcatalogue.json_catalogue) == 1
    (public,) = beqcatalogue.json_catalogue
    beqcatalogue.finalise_catalogue_entry(public)
    (tmp_path / 'docs' / 'database.json').write_text(json.dumps(beqcatalogue.json_catalogue), encoding='utf-8')
    assert public['title'] == record['title']
    assert public['catalogue_url'].endswith(f'/{author}/fixture-film/#dts-hdma-51')
    assert public['audioCodecs'] == ['DTS-HD MA']
    assert public['audioChannelCounts'] == ['5.1']
    assert public['filterAuthor'] == 'human'
    assert public['created_at'] == public['updated_at'] == 100


def test_record_input_script_clones_and_updates_the_configured_repo(tmp_path):
    remote = tmp_path / 'remote.git'
    seed = tmp_path / 'seed'
    subprocess.run(['git', 'init', '--bare', '-b', 'main', str(remote)], check=True, capture_output=True)
    subprocess.run(['git', 'clone', str(remote), str(seed)], check=True, capture_output=True)
    env = {**os.environ, 'BEQCATALOGUE_FILTER_REPO_URL': str(remote),
           'GIT_AUTHOR_NAME': 'Fixture', 'GIT_AUTHOR_EMAIL': 'fixture@example.test',
           'GIT_COMMITTER_NAME': 'Fixture', 'GIT_COMMITTER_EMAIL': 'fixture@example.test'}

    def publish(text):
        (seed / 'movies').mkdir(exist_ok=True)
        (seed / 'movies' / 'fixture.json').write_text(text, encoding='utf-8')
        subprocess.run(['git', '-C', str(seed), 'add', '.'], check=True, capture_output=True, env=env)
        subprocess.run(['git', '-C', str(seed), 'commit', '-m', 'fixture'], check=True, capture_output=True, env=env)
        subprocess.run(['git', '-C', str(seed), 'push', 'origin', 'main'], check=True, capture_output=True, env=env)

    publish('{"version": 1}')
    subprocess.run([str(ROOT / 'update_record_input.sh')], cwd=tmp_path, env=env, check=True, capture_output=True)
    fetched = tmp_path / beqcatalogue.RECORD_REPO_CONFIGS[0][1] / 'movies' / 'fixture.json'
    assert fetched.read_text(encoding='utf-8') == '{"version": 1}'
    publish('{"version": 2}')
    subprocess.run([str(ROOT / 'update_record_input.sh')], cwd=tmp_path, env=env, check=True, capture_output=True)
    assert fetched.read_text(encoding='utf-8') == '{"version": 2}'
