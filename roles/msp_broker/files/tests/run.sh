#!/bin/sh
# Unit tests for the broker core. Runs anywhere: temp roots only, no root, no network.
here=$(cd "$(dirname "$0")" && pwd)
lib=$(cd "$here/.." && pwd)
export PYTHONPATH="$lib${PYTHONPATH:+:$PYTHONPATH}"
cd "$here" || exit 1
python3 -m unittest discover -s . -p 'test_*.py' -v
