#!/usr/bin/env bash
# S1-0 part C section 3: CI and Extended history from GitHub (no local test runs). Needs an authenticated gh.
#   bash docs/s1/evidence/fetch_ci_history.sh [CI runs, default 180] [Extended runs, default 80]
# Writes, under docs/s1/evidence/data/:
#   ci_runs.tsv   one line per run: workflow, run id, event, branch, conclusion, attempt, created, updated, head sha
#   ci_jobs.tsv   one line per job of every attempt (jobs?filter=all): workflow, run id, attempt, job name,
#                 conclusion, created, started, completed
set -eu
n_ci=${1:-180}; n_ext=${2:-80}
repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
d="docs/s1/evidence/data"
mkdir -p "$d"
: > "$d/ci_runs.tsv"
for spec in "ci.yml $n_ci" "extended.yml $n_ext"; do
  set -- $spec; wf=$1; n=$2
  gh run list --workflow "$wf" --limit "$n" \
    --json databaseId,event,headBranch,conclusion,attempt,createdAt,updatedAt,headSha \
    --jq ".[] | [\"$wf\", .databaseId, .event, .headBranch, .conclusion, .attempt, .createdAt, .updatedAt, .headSha] | @tsv" \
    >> "$d/ci_runs.tsv"
done
: > "$d/ci_jobs.tsv"
while IFS=$'\t' read -r wf id event branch conclusion attempt created updated sha; do
  # the #344 pull request's runs are the dedup's ~20 s skip: they hold no test job
  gh api --paginate "repos/$repo/actions/runs/$id/jobs?filter=all&per_page=100" \
    --jq ".jobs[] | [\"$wf\", $id, .run_attempt, .name, .conclusion, .created_at, .started_at, .completed_at] | @tsv" \
    >> "$d/ci_jobs.tsv"
done < "$d/ci_runs.tsv"
wc -l "$d/ci_runs.tsv" "$d/ci_jobs.tsv"
# Extended's push runs on the integration branch are a minority of its runs (feature branches dispatch it before a
# merge): top them up to 35, then fetch the jobs of the runs not fetched above.
gh run list --workflow extended.yml --branch redesign/visual-editor --event push --limit 35 \
  --json databaseId,event,headBranch,conclusion,attempt,createdAt,updatedAt,headSha \
  --jq '.[] | ["extended.yml", .databaseId, .event, .headBranch, .conclusion, .attempt, .createdAt, .updatedAt, .headSha] | @tsv' \
  | while IFS=$'\t' read -r wf id rest; do
      grep -q "	$id	" "$d/ci_runs.tsv" && continue
      printf '%s\t%s\t%s\n' "$wf" "$id" "$rest" >> "$d/ci_runs.tsv"
      gh api --paginate "repos/$repo/actions/runs/$id/jobs?filter=all&per_page=100" \
        --jq ".jobs[] | [\"$wf\", $id, .run_attempt, .name, .conclusion, .created_at, .started_at, .completed_at] | @tsv" \
        >> "$d/ci_jobs.tsv"
    done
wc -l "$d/ci_runs.tsv" "$d/ci_jobs.tsv"
