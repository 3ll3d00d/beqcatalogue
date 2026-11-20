'''Declarative metadata corrections for catalogue entries.

Some authors' entries can't be fixed at source: aron7awol and mobe1969 are frozen (their
entries are carried forward from the previous docs/database.json rather than re-read), so
data-quality fixes for them live in ``meta/entry_patches.json`` instead.

Each patch identifies one entry by ``author`` + ``underlying`` (the source file name, which is
unique per author and stable across regeneration) and lists the fields to ``set``.  ``expect``
optionally pins the value a field must currently have; if the entry has drifted to something
else (e.g. the upstream data was itself corrected differently) the patch is skipped and
reported rather than overwriting it.  Applying is idempotent, so the build re-applies every
patch on each run: a no-op for entries already patched in place, and a re-fix for any entry
that is ever regenerated from source.

``digest`` is deliberately left untouched even though it hashes the title: it is the entry's
identity for ezbeq and the device catalogues, and the filters it describes haven't changed.
'''
import json
import os
from dataclasses import dataclass, field

DEFAULT_PATCH_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'meta',
                                  'entry_patches.json')


@dataclass
class PatchReport:
    applied: list[tuple[dict, dict]] = field(default_factory=list)  # (patch, {field: (old, new)})
    already: list[dict] = field(default_factory=list)
    conflicts: list[tuple[dict, str]] = field(default_factory=list)
    unmatched: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f'Entry patches: {len(self.applied)} applied, {len(self.already)} already applied, '
                 f'{len(self.conflicts)} conflicts, {len(self.unmatched)} unmatched']
        for p, why in self.conflicts:
            lines.append(f'  conflict {p["author"]} / {p["underlying"]}: {why}')
        for p in self.unmatched:
            lines.append(f'  unmatched {p["author"]} / {p["underlying"]}')
        return '\n'.join(lines)


def load_patches(path: str = DEFAULT_PATCH_FILE) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        patches = json.load(f)
    for p in patches:
        if not p.get('author') or not p.get('underlying') or not p.get('set'):
            raise ValueError(f'Invalid entry patch, needs author, underlying and set: {p}')
    return patches


def apply_entry_patches(entries: list[dict], patches: list[dict]) -> PatchReport:
    '''Apply patches in place to database.json-shaped entries.'''
    report = PatchReport()
    by_key = {(e.get('author'), e.get('underlying')): e for e in entries}
    for p in patches:
        entry = by_key.get((p['author'], p['underlying']))
        if entry is None:
            report.unmatched.append(p)
            continue
        target = p['set']
        # an absent field reads as '' (frozen film entries have no season/episode keys)
        if all(k in entry and entry[k] == v for k, v in target.items()):
            report.already.append(p)
            continue
        drifted = [k for k, v in p.get('expect', {}).items()
                   if entry.get(k, '') != v and entry.get(k, '') != target.get(k)]
        if drifted:
            report.conflicts.append((p, ', '.join(f'{k}={entry.get(k, "")!r}, expected {p["expect"][k]!r}'
                                                  for k in drifted)))
            continue
        changes = {}
        for k, v in target.items():
            if k not in entry or entry[k] != v:
                changes[k] = (entry.get(k, ''), v)
                entry[k] = v
        if 'title' in changes and 'sortTitle' not in target:
            old_title, new_title = changes['title']
            if entry.get('sortTitle', '').casefold() == (old_title or '').casefold():
                entry['sortTitle'] = new_title.casefold()
        report.applied.append((p, changes))
    return report
