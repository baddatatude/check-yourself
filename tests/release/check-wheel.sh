#!/usr/bin/env bash
set -euo pipefail
python_bin=${PYTHON:-python3}
source_dir=$(cd "$(dirname "$0")/../.." && pwd)
wheel=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
export PATH="/usr/games:$PATH"

for environment in core html legacy; do
  "$python_bin" -m venv "$scratch/$environment"
  target=$wheel
  if [[ $environment != core ]]; then target="${wheel}[$environment]"; fi
  "$scratch/$environment/bin/python" -m pip install "$target"
  "$scratch/$environment/bin/python" -m pip check
  "$scratch/$environment/bin/python" -m pip freeze
done

mkdir "$scratch/run" "$scratch/guard"
cp "$source_dir/tests/release/network_guard.py" "$scratch/guard/sitecustomize.py"
cd "$scratch/run"
export PYTHONPATH="$scratch/guard" PYTHONNOUSERSITE=1
"$scratch/core/bin/python" "$source_dir/tests/release/smoke.py"
"$scratch/core/bin/check-yourself" analyze-pgn --help
"$scratch/core/bin/check-yourself" analyze-pgn single.pgn --color black --depth 6 -o single.json
"$scratch/html/bin/check-yourself" analyze-pgn batch.pgn --player Alice --depth 6 \
  -o batch.json --html batch.html
"$scratch/html/bin/python" "$source_dir/tests/browser/generate_reports.py" "$scratch/reports" \
  --browser-check "$source_dir/tests/browser/check_report.js"
"$scratch/legacy/bin/python" -c 'import check_yourself.pipeline, httpx'
if [[ -n ${CHROME_BIN:-} ]]; then
  for report in single multi; do
    "$CHROME_BIN" --headless --no-first-run --disable-background-networking \
      '--host-resolver-rules=MAP * ~NOTFOUND' --virtual-time-budget=15000 \
      "--user-data-dir=$scratch/chrome" --dump-dom \
      "file://$scratch/reports/$report-browser.html" > "$scratch/$report-dom.html"
    grep -o 'data-browser-check="[^"]*"' "$scratch/$report-dom.html"
    grep -q 'data-browser-check="PASS"' "$scratch/$report-dom.html"
  done
fi
