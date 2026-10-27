#!/bin/sh
# check.sh: the one command that proves this repo works.
#
# Created 2026-10-27 by the repo docs pass. It wraps the gates this repo ALREADY declares, and it adds
# nothing of its own: a check that re-tests what the suite already tests is a second truth.
#
# Gate: npm, read from the repo itself.
#
# Exit codes: 0 the repo works, non-zero the repo does not. Never "0 with warnings".
set -e
cd "$(dirname "$0")"
echo "== npm test"
npm test
echo "check.sh: green on $(date -u +%Y-%m-%dT%H:%M:%SZ)"
