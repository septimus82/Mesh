#!/usr/bin/env bash
# S1-0 part C section 2: drive mutation_probe.py's mutants, ONE Python process at a time (the owner's CPU rule).
#   bash docs/s1/evidence/mutation_run.sh <group>      (from the repository root; PY defaults to "py -3.13")
# Per group: copy the module aside, run its own tests unmutated (must pass), then per mutant: apply it (one short
# Python process), run the tests (one pytest process), copy the module back and check its SHA-256 and git status.
# Appends one JSON line per run to docs/s1/evidence/data/mutation_results.jsonl.
set -u
group="$1"
PY=${PY:-"py -3.13"}
here="docs/s1/evidence"
out="$here/data/mutation_results.jsonl"
plan=$($PY "$here/mutation_probe.py" --plan | awk -F'\t' -v g="$group" '$1 == g')
[ -n "$plan" ] || { echo "no group $group"; exit 2; }
module=$(printf '%s' "$plan" | cut -f2)
tests=$(printf '%s' "$plan" | cut -f3)
mutants=$(printf '%s' "$plan" | cut -f4)
git diff --quiet -- "$module" || { echo "refusing: $module has uncommitted changes"; exit 2; }
backup=$(mktemp)
cp -p "$module" "$backup"
want=$(sha256sum < "$module" | cut -d' ' -f1)
export PYTHONPATH="$PWD" PYTHONDONTWRITEBYTECODE=1

run_tests() {  # -> sets code, secs, line
  local log start end
  log=$(mktemp)
  start=$(date +%s)
  # shellcheck disable=SC2086
  $PY -m pytest -q -x -p no:cacheprovider $tests > "$log" 2>&1
  code=$?
  end=$(date +%s)
  secs=$((end - start))
  line=$(grep -m1 -E '^(FAILED|ERROR) ' "$log" || grep -v '^\s*$' "$log" | tail -1)
  line=${line:0:200}
  rm -f "$log"
}

record() {  # id verdict
  local esc=${line//\\/\\\\}; esc=${esc//\"/\\\"}
  printf '{"group":"%s","id":"%s","module":"%s","exit":%s,"verdict":"%s","seconds":%s,"line":"%s"}\n' \
    "$group" "$1" "$module" "$code" "$2" "$secs" "$esc" >> "$out"
}

restore() {
  cp -p "$backup" "$module"
  [ "$(sha256sum < "$module" | cut -d' ' -f1)" = "$want" ] || { echo "ERROR: $module not restored"; exit 3; }
}
trap restore EXIT

run_tests
echo "[$group] baseline: exit $code ${secs}s | $line"
record baseline "$([ "$code" = 0 ] && echo green || echo red)"
[ "$code" = 0 ] || { echo "baseline not green: no mutants run"; exit 1; }

for mid in $mutants; do
  $PY "$here/mutation_probe.py" --apply "$group" "$mid" || { restore; echo "apply $mid failed"; exit 2; }
  run_tests
  restore
  verdict=$([ "$code" = 0 ] && echo SURVIVED || echo killed)
  echo "[$group] $mid $verdict exit $code ${secs}s | $line"
  record "$mid" "$verdict"
done
trap - EXIT
rm -f "$backup"
git diff --quiet -- "$module" || { echo "ERROR: $module differs from git"; exit 3; }
