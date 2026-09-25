"""The version-1 JSON reader must reach the generated public database."""
import csv
import json
from collections import defaultdict

import beqcatalogue


def test_source_record_is_processed_and_finalised(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    record = {
        'title': 'Fixture Film', 'year': '2024', 'audioTypes': ['DTS-HD.MA 5.1'],
        'content_type': 'film', 'author': 'fixture', 'filters': [], 'mv': '0',
        'created_at': 100, 'updated_at': 100,
    }
    record['digest'] = beqcatalogue.digest(record)
    (source / 'fixture.json').write_text(json.dumps(record), encoding='utf-8')
    (source / 'database.json').write_text(json.dumps([record]), encoding='utf-8')
    (tmp_path / 'docs').mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(beqcatalogue, 'error_files', defaultdict(list), raising=False)
    monkeypatch.setattr(beqcatalogue, 'source_record_times', {})
    monkeypatch.setattr(beqcatalogue, 'json_catalogue', [], raising=False)
    monkeypatch.setattr(beqcatalogue, 'times', {'fixture': {}}, raising=False)
    with (tmp_path / 'database.csv').open('w', newline='') as handle:
        monkeypatch.setattr(beqcatalogue, 'db_writer', csv.writer(handle), raising=False)
        extracted = beqcatalogue.extract_filter_records(str(source), 'fixture')
        assert len(extracted) == 1
        beqcatalogue.process_content_from_repo('fixture', extracted, [], 'film', [])
    assert beqcatalogue.error_files['fixture'] == []
    assert len(beqcatalogue.json_catalogue) == 1
    (public,) = beqcatalogue.json_catalogue
    beqcatalogue.finalise_catalogue_entry(public)
    assert public['title'] == record['title']
    assert public['catalogue_url'].endswith('/fixture/fixture-film/#dts-hdma-51')
    assert public['audioCodecs'] == ['DTS-HD MA']
    assert public['audioChannelCounts'] == ['5.1']
    assert public['filterAuthor'] == 'human'
    assert public['created_at'] == public['updated_at'] == 100
