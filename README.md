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
