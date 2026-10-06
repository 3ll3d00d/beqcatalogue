"""Runs tests/js/devices.test.mjs against real optimiser results (needs node and beqoptimiser)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from iir import LowShelf, PeakingEQ

ROOT = Path(__file__).resolve().parents[1]


def published(filt, count=1):
    return {**filt.to_map(), 'count': count}


def test_browser_maths_matches_optimiser(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('node not installed')
    pytest.importorskip('beqoptimiser')
    from beqoptimiser.cli import optimise_entry

    raw = [
        ('peak 10 Hz q0.7 +12', [{'type': 'PeakingEQ', 'freq': 10.0, 'gain': 12.0, 'q': 0.7, 'count': 1}]),
        ('peak 10 Hz q2 +12', [{'type': 'PeakingEQ', 'freq': 10.0, 'gain': 12.0, 'q': 2.0, 'count': 1}]),
        ('published shelves', [published(LowShelf(96000, 20.0, 0.9, 5.0), 3),
                               published(PeakingEQ(96000, 8.0, 1.5, 6.0))]),
    ]
    cases = []
    for name, filters in raw:
        for rate in (48000, 96000):
            report = optimise_entry({'filters': filters, 'mv': '0'}, rate=rate, cache=False)
            result, variant = report['result'], report['variant']
            cases.append({'name': f'{name} @ {rate}', 'rate': rate, 'filters': filters,
                          'before_db': result['original_error_db'],
                          'after': variant['biquads'] if variant else None,
                          'after_db': result['candidate_error_db'] if variant else None})
    assert any(c['after'] for c in cases)
    assert any(c['filters'][0].get('biquads') for c in cases)
    path = tmp_path / 'cases.json'
    path.write_text(json.dumps(cases))
    run = subprocess.run([node, str(ROOT / 'tests' / 'js' / 'devices.test.mjs'), str(path)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
