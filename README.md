# beqcatalogue

Generates a catalogue of BEQs in markdown format from the BEQ avs thread

# Rebuilding the catalogue remotely

## Setup

1) create a personal access token (user profile > settings > developer settings > personal access tokens or https://github.com/settings/tokens) with the public repo entitlements
2) add that token as a secret named `TRIGGER_BEQCATALOGUE` in your repo (repo settings > secrets)
3) create a workflow in your repo as per https://github.com/3ll3d00d/beqcatalogue/blob/master/.github/workflows/trigger.yaml (i.e. copy this file to your repo)

## Testing

Push a change to your repo
The trigger workflow should complete successfully
Check the repo rebuilds ok - https://github.com/3ll3d00d/beqcatalogue/actions?query=workflow%3A%22update+catalogue%22+event%3Arepository_dispatch

## Notes

first.csv generated (v slowly) using

    git ls-files -z | xargs -0 -n1 -I{} -- git --no-pager log --diff-filter=A --follow --format="\"{}\",%at" {} | sort

last.csv generated using

    git ls-files -z | xargs -0 -n1 -I{} -- git log -1 --format="\"{}\",%at" {} | sort

## BEQDesigner JSON filter records

The catalogue build fetches `3ll3d00d/beqfilters` into
`.input/3ll3d00d/beqfilters` through `update_record_input.sh` and reads its
individual version-1 JSON records under author `3ll3d00d`. The producer's
`database.json` is a derived cache and is skipped. `3ll3d00d/beqimgs` is the
separate image repository; source records carry image URLs, so this build does
not clone the image repository.

## Device-specific optimised catalogues

Devices store filter coefficients with finite precision. beqforge's `beqoptimiser` searches for
coefficients whose realised response better matches the authored filter. `beqcatalogue/devices.py`
publishes one catalogue per format profile committed in `devices/profiles/<id>.json`:

* `docs/devices/<id>.json`: main catalogue `digest` -> optimised biquads, only for entries the
  optimiser replaced
* `meta/devices/<id>.tsv`: every evaluated digest and its outcome, so nothing is re-optimised
* `docs/devices/{index,titles}.json`, `compare/`, `pages/`: data for the Device optimisation page
  and the title-page "Optimised for…" badges

The `update catalogue` workflow runs this after the main build: `device-matrix` lists the
profiles with unevaluated digests, one `device-catalogue` job per profile evaluates them in
parallel (time-budgeted, with a cached optimiser result store), and `device-publish` commits.

* **Add a profile**: commit a new `devices/profiles/<id>.json`; it joins the matrix on the next run.
* **Re-evaluate a profile** (e.g. after upgrading beqforge): bump its `revision`. Changing its
  numerical config without a revision bump fails the build.
* **Bootstrap locally** from the optimiser cache (needs `poetry install --with optimiser`):

      poetry run python beqcatalogue/devices.py bootstrap --cache-dir ~/.cache/beqoptimiser --workers 12
