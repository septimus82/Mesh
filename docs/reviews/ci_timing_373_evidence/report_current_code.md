# verify-all step-budget reliability on CI

Runs: 48 (linux 24, windows 24). Budgets: verify_step_budget.json.

## linux

### linux: per-step distribution, 24 post-opt runs

| step | median s | p90 s | max s | max/median | CV | threshold s | threshold/median | over (post-opt) | over (pre-opt) |
|---|---|---|---|---|---|---|---|---|---|
| pytest-fast | 79.18 | 82.09 | 85.69 | 1.08 | 0.11 | 79.05 | 1.00 | 12/24 (50%) | - |
| mypy-gate | 13.85 | 26.83 | 27.75 | 2.00 | 0.43 | - | - | - | - |
| verify-demo | 10.38 | 10.79 | 11.21 | 1.08 | 0.18 | 13.02 | 1.25 | 0/24 (0%) | - |
| web-smoke | 3.85 | 4.03 | 4.20 | 1.09 | 0.11 | 5.17 | 1.34 | 0/24 (0%) | - |
| swallow-scan-gate | 3.50 | 3.77 | 4.15 | 1.19 | 0.11 | - | - | - | - |
| exception-policy-scan | 3.28 | 3.53 | 3.92 | 1.20 | 0.11 | 3.56 | 1.08 | 1/24 (4%) | - |
| player-package-gate | 1.14 | 1.18 | 1.24 | 1.09 | 0.13 | 2.07 | 1.82 | 0/24 (0%) | - |
| verify-strict | 0.59 | 0.60 | 0.61 | 1.05 | 0.16 | - | - | - | - |
| encounter-audit | 0.35 | 0.37 | 0.37 | 1.06 | 0.16 | - | - | - | - |

### linux: runner speed factor (median of 8 reference steps: encounter-audit, exception-policy-scan, player-package-gate, pytest-fast, swallow-scan-gate, verify-demo, verify-strict, web-smoke)

Speed factor over 24 runs: min 0.66, median 1.01, max 1.08; slowest/fastest 1.63; sd of log 0.132.

| step | corr with other steps' speed | slope | variance explained | sd log (raw) | sd log (residual) | residual drift corr | runner-adjusted growth, first to last run |
|---|---|---|---|---|---|---|---|
| encounter-audit | 0.97 | 1.44 | 0.93 | 0.183 | 0.048 | 0.14 | 1.023 |
| exception-policy-scan | 0.81 | 0.66 | 0.65 | 0.115 | 0.068 | -0.24 | 0.948 |
| mypy-gate | 0.21 | 0.97 | 0.04 | 0.614 | 0.600 | -0.15 | 0.735 |
| player-package-gate | 0.97 | 0.99 | 0.94 | 0.133 | 0.034 | -0.45 | 0.951 |
| pytest-fast | 0.98 | 0.81 | 0.96 | 0.117 | 0.022 | 0.36 | 1.027 |
| swallow-scan-gate | 0.87 | 0.69 | 0.75 | 0.112 | 0.056 | -0.18 | 0.967 |
| verify-demo | 0.96 | 1.54 | 0.92 | 0.197 | 0.054 | -0.01 | 0.998 |
| verify-strict | 0.98 | 1.34 | 0.95 | 0.170 | 0.036 | 0.16 | 1.019 |
| web-smoke | 0.89 | 0.80 | 0.79 | 0.121 | 0.055 | 0.13 | 1.024 |

Runs, slowest first (flagged = steps over the current thresholds):

| run | sha | event | speed | rank | flagged |
|---|---|---|---|---|---|
| 40509194015 | 1d2501d | push | 1.08 | 1 | exception-policy-scan, pytest-fast |
| 40480507815 | 75b8d8e | push | 1.04 | 2 | pytest-fast |
| 40482662005 | ec51e36 | pull_request | 1.04 | 3 | pytest-fast |
| 40540237224 | 0fbbef1 | pull_request | 1.04 | 4 | pytest-fast |
| 40537734129 | 4eb6667 | pull_request | 1.04 | 5 | pytest-fast |
| 40545138940 | 8613110 | push | 1.03 | 6 | pytest-fast |
| 40530270399 | 043d7b8 | push | 1.03 | 7 | pytest-fast |
| 40537523338 | 49c2769 | pull_request | 1.02 | 8 | pytest-fast |
| 40537124494 | abdcf1c | push | 1.01 | 9 | pytest-fast |
| 40502056355 | bf8bbd3 | pull_request | 1.01 | 10 | pytest-fast |
| 40509204836 | 1d2501d | pull_request | 1.01 | 11 | pytest-fast |
| 40537509580 | 49c2769 | push | 1.01 | 12 | pytest-fast |
| 40480510061 | 75b8d8e | pull_request | 1.01 | 13 | - |
| 40537724584 | 4eb6667 | push | 0.99 | 14 | - |
| 40465949215 | 8216592 | push | 0.98 | 15 | - |
| 40545149744 | 8613110 | pull_request | 0.98 | 16 | - |
| 40545051504 | 19a4c5d | push | 0.97 | 17 | - |
| 40540198141 | 0fbbef1 | push | 0.90 | 18 | - |
| 40545056320 | 19a4c5d | pull_request | 0.80 | 19 | - |
| 40530276385 | 043d7b8 | pull_request | 0.79 | 20 | - |
| 40537135746 | abdcf1c | pull_request | 0.78 | 21 | - |
| 40482657756 | ec51e36 | push | 0.78 | 22 | - |
| 40465951252 | 8216592 | pull_request | 0.76 | 23 | - |
| 40502049562 | bf8bbd3 | push | 0.66 | 24 | - |

Same commit, push vs pull_request (12 pairs): PR/push speed ratio median 0.96, range 0.77-1.53; correlation of the two runs' speed factors -0.30; PR slower in 5/12.

### linux: policies (k = 4.0; cross-validated over 24 post-opt runs)

Checked steps: current rule exception-policy-scan, player-package-gate, pytest-fast, verify-demo, web-smoke; other rules exception-policy-scan, mypy-gate, player-package-gate, pytest-fast, swallow-scan-gate, verify-demo, web-smoke. Detection = the regressed step itself is flagged. Uniform = every step x1.3; runner-like = every step x1.3**slope (the slopes in the speed table), i.e. the way the observed runners differ; both count runs with any step flagged.

| policy | false failures (runs) | uniform x1.3 fails | runner-like x1.3 fails | pytest-fast x1.25 | pytest-fast x1.5 | pytest-fast x2.0 | verify-demo x1.25 | verify-demo x1.5 | verify-demo x2.0 | mypy-gate x1.25 | mypy-gate x1.5 | mypy-gate x2.0 | exception-policy-scan x1.25 | exception-policy-scan x1.5 | exception-policy-scan x2.0 | swallow-scan-gate x1.25 | swallow-scan-gate x1.5 | swallow-scan-gate x2.0 | web-smoke x1.25 | web-smoke x1.5 | web-smoke x2.0 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a. current rule (committed budgets) | 12/24 (50%) | 23/24 (96%) | 22/24 (92%) | 88% | 100% | 100% | 50% | 75% | 96% | not checked | not checked | not checked | 83% | 96% | 100% | not checked | not checked | not checked | 8% | 83% | 100% |
| x. same-run total normalisation (unsafe) | 0/24 (0%) | 0/24 (0%) | 0/24 (0%) | 0% | 4% | 4% | 4% | 54% | 100% | 0% | 0% | 0% | 4% | 58% | 100% | 4% | 79% | 100% | 12% | 79% | 100% |
| b1. leave-one-out speed, unit slope | 2/24 (8%) | 2/24 (8%) | 1/24 (4%) | 100% | 100% | 100% | 0% | 79% | 100% | 0% | 0% | 0% | 8% | 75% | 100% | 8% | 100% | 100% | 8% | 100% | 100% |
| B. recommended: leave-one-out speed, fitted slope | 3/24 (12%) | 2/24 (8%) | 2/24 (8%) | 100% | 100% | 100% | 42% | 100% | 100% | 0% | 0% | 0% | 8% | 96% | 100% | 33% | 100% | 100% | 12% | 100% | 100% |
| A. advisory model (B as verify-all evaluates it) | 3/24 (12%) | 2/24 (8%) | 2/24 (8%) | 100% | 100% | 100% | 46% | 100% | 100% | 0% | 0% | 0% | 8% | 96% | 100% | 42% | 100% | 100% | 17% | 100% | 100% |
| b3. B + speed cap | 3/24 (12%) | 16/24 (67%) | 7/24 (29%) | 100% | 100% | 100% | 42% | 100% | 100% | 0% | 0% | 0% | 8% | 96% | 100% | 33% | 100% | 100% | 12% | 100% | 100% |
| c1. per-platform limit, k*sigma of log time | 0/24 (0%) | 1/24 (4%) | 0/24 (0%) | 0% | 17% | 96% | 0% | 0% | 21% | 0% | 0% | 0% | 0% | 33% | 96% | 0% | 29% | 96% | 0% | 8% | 92% |
| c2. per-platform limit, slowest/median + 0.10 | 1/24 (4%) | 21/24 (88%) | 18/24 (75%) | 67% | 96% | 100% | 71% | 75% | 100% | 21% | 21% | 38% | 38% | 83% | 100% | 33% | 88% | 100% | 75% | 88% | 100% |
| e. external calibration (job's full pytest) | 0/24 (0%) | 1/24 (4%) | 0/24 (0%) | 0% | 46% | 79% | 0% | 0% | 58% | 0% | 0% | 0% | 0% | 17% | 92% | 0% | 25% | 92% | 0% | 21% | 92% |
| f. a and A both (fixed ceiling and advisory) | 0/24 (0%) | 1/24 (4%) | 1/24 (4%) | 88% | 100% | 100% | 21% | 75% | 96% | 0% | 0% | 0% | 8% | 96% | 100% | 0% | 0% | 0% | 8% | 83% | 100% |

Historical runs each rule fails (cross-validated):

| policy | run | sha | event | flagged |
|---|---|---|---|---|
| a. current rule (committed budgets) | 40480507815 | 75b8d8e | push | pytest-fast |
| a. current rule (committed budgets) | 40482662005 | ec51e36 | pull_request | pytest-fast |
| a. current rule (committed budgets) | 40502056355 | bf8bbd3 | pull_request | pytest-fast |
| a. current rule (committed budgets) | 40509194015 | 1d2501d | push | exception-policy-scan, pytest-fast |
| a. current rule (committed budgets) | 40509204836 | 1d2501d | pull_request | pytest-fast |
| a. current rule (committed budgets) | 40530270399 | 043d7b8 | push | pytest-fast |
| a. current rule (committed budgets) | 40537124494 | abdcf1c | push | pytest-fast |
| a. current rule (committed budgets) | 40537509580 | 49c2769 | push | pytest-fast |
| a. current rule (committed budgets) | 40537523338 | 49c2769 | pull_request | pytest-fast |
| a. current rule (committed budgets) | 40537734129 | 4eb6667 | pull_request | pytest-fast |
| a. current rule (committed budgets) | 40540237224 | 0fbbef1 | pull_request | pytest-fast |
| a. current rule (committed budgets) | 40545138940 | 8613110 | push | pytest-fast |
| b1. leave-one-out speed, unit slope | 40465951252 | 8216592 | pull_request | exception-policy-scan, player-package-gate, swallow-scan-gate |
| b1. leave-one-out speed, unit slope | 40482657756 | ec51e36 | push | web-smoke |
| B. recommended: leave-one-out speed, fitted slope | 40465951252 | 8216592 | pull_request | exception-policy-scan, player-package-gate |
| B. recommended: leave-one-out speed, fitted slope | 40482657756 | ec51e36 | push | web-smoke |
| B. recommended: leave-one-out speed, fitted slope | 40502049562 | bf8bbd3 | push | verify-demo |
| A. advisory model (B as verify-all evaluates it) | 40465951252 | 8216592 | pull_request | exception-policy-scan, player-package-gate |
| A. advisory model (B as verify-all evaluates it) | 40482657756 | ec51e36 | push | web-smoke |
| A. advisory model (B as verify-all evaluates it) | 40502049562 | bf8bbd3 | push | verify-demo |
| b3. B + speed cap | 40465951252 | 8216592 | pull_request | exception-policy-scan, player-package-gate |
| b3. B + speed cap | 40482657756 | ec51e36 | push | web-smoke |
| b3. B + speed cap | 40502049562 | bf8bbd3 | push | verify-demo |
| c2. per-platform limit, slowest/median + 0.10 | 40509194015 | 1d2501d | push | exception-policy-scan |



### linux: uniform regressions via the rolling median of the run speed factor

Per-run speed sd of log 0.135 over 24 runs.

| window (runs) | rolling median speed, observed range | sd of log median (iid) | detectable uniform slowdown, 3 sd | 4 sd |
|---|---|---|---|---|
| 5 | 0.97-1.02 | 0.075 | 1.25 | 1.35 |
| 10 | 1.00-1.01 | 0.053 | 1.17 | 1.24 |
| 20 | 1.01-1.01 | 0.038 | 1.12 | 1.16 |

A persistent isolated regression, judged on the median of the runner-adjusted residuals of the last n runs (smallest factor above 4 sd):

| step | residual sigma | per run | median of 5 runs | median of 10 runs | median of 20 runs |
|---|---|---|---|---|---|
| pytest-fast | 0.023 | 1.10 | 1.05 | 1.04 | 1.03 |
| verify-demo | 0.057 | 1.25 | 1.14 | 1.09 | 1.07 |
| mypy-gate | 0.627 | 12.27 | 4.08 | 2.70 | 2.02 |
| exception-policy-scan | 0.071 | 1.33 | 1.17 | 1.12 | 1.08 |
| swallow-scan-gate | 0.058 | 1.26 | 1.14 | 1.10 | 1.07 |
| web-smoke | 0.058 | 1.26 | 1.14 | 1.10 | 1.07 |

### linux: re-run on failure (median job 9.3 min)

Repeating verify-all inside the same job would add about 2.0 min per run (sum of step medians) and cannot remove the runner-level part of the variance (the 'variance explained' column of the speed table).

| policy | first-attempt false failures | false failures after one re-run | extra job min per run | pytest-fast x1.25 (one try -> both tries) | pytest-fast x1.5 (one try -> both tries) | pytest-fast x2.0 (one try -> both tries) | exception-policy-scan x1.25 (one try -> both tries) | exception-policy-scan x1.5 (one try -> both tries) | exception-policy-scan x2.0 (one try -> both tries) | verify-demo x1.25 (one try -> both tries) | verify-demo x1.5 (one try -> both tries) | verify-demo x2.0 (one try -> both tries) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a. current rule | 12/24 (50%) | 23.9% | 4.63 | 88% -> 76% | 100% -> 100% | 100% -> 100% | 83% -> 69% | 96% -> 92% | 100% -> 100% | 50% -> 24% | 75% -> 55% | 96% -> 92% |
| B. recommended | 3/24 (12%) | 1.1% | 1.16 | 100% -> 100% | 100% -> 100% | 100% -> 100% | 8% -> 0% | 96% -> 92% | 100% -> 100% | 42% -> 16% | 100% -> 100% | 100% -> 100% |

### linux: recommended rule, sensitivity to k

| k | false failures | pytest-fast x1.25 | pytest-fast x1.5 | exception-policy-scan x1.25 | exception-policy-scan x1.5 | verify-demo x1.25 | verify-demo x1.5 | web-smoke x1.25 | web-smoke x1.5 |
|---|---|---|---|---|---|---|---|---|---|
| 3.0 | 3/24 (12%) | 100% | 100% | 50% | 96% | 88% | 100% | 88% | 100% |
| 3.5 | 3/24 (12%) | 100% | 100% | 17% | 96% | 62% | 100% | 67% | 100% |
| 4.0 | 3/24 (12%) | 100% | 100% | 8% | 96% | 42% | 100% | 12% | 100% |
| 4.5 | 2/24 (8%) | 100% | 100% | 8% | 88% | 17% | 100% | 12% | 100% |

### linux: recommended rule parameters (all post-opt runs)

| step | median s | slope b | residual sigma | allowed ratio over expectation | max speed seen (other steps) | current threshold/median |
|---|---|---|---|---|---|---|
| exception-policy-scan | 3.28 | 0.66 | 0.071 | 1.34 | 1.08 | 1.08 |
| mypy-gate | 13.85 | 0.97 | 0.627 | 12.93 | 1.08 | - |
| player-package-gate | 1.14 | 0.99 | 0.035 | 1.16 | 1.08 | 1.82 |
| pytest-fast | 79.18 | 0.81 | 0.023 | 1.10 | 1.08 | 1.00 |
| swallow-scan-gate | 3.50 | 0.69 | 0.058 | 1.27 | 1.08 | - |
| verify-demo | 10.38 | 1.54 | 0.057 | 1.26 | 1.08 | 1.25 |
| web-smoke | 3.85 | 0.80 | 0.058 | 1.27 | 1.08 | 1.34 |

## windows

### windows: per-step distribution, 24 post-opt runs

| step | median s | p90 s | max s | max/median | CV | threshold s | threshold/median | over (post-opt) | over (pre-opt) |
|---|---|---|---|---|---|---|---|---|---|
| pytest-fast | 124.66 | 135.82 | 142.54 | 1.14 | 0.19 | 121.82 | 0.98 | 13/24 (54%) | - |
| verify-demo | 21.82 | 24.94 | 25.50 | 1.17 | 0.28 | 25.69 | 1.18 | 0/24 (0%) | - |
| mypy-gate | 17.08 | 32.64 | 36.20 | 2.12 | 0.48 | - | - | - | - |
| web-smoke | 5.40 | 5.69 | 5.99 | 1.11 | 0.17 | 7.12 | 1.32 | 0/24 (0%) | - |
| swallow-scan-gate | 3.83 | 4.48 | 5.66 | 1.48 | 0.20 | - | - | - | - |
| exception-policy-scan | 3.46 | 4.16 | 5.18 | 1.50 | 0.18 | 3.74 | 1.08 | 6/24 (25%) | - |
| player-package-gate | 1.87 | 2.03 | 2.25 | 1.20 | 0.20 | 2.91 | 1.56 | 0/24 (0%) | - |
| verify-strict | 0.95 | 1.06 | 1.11 | 1.16 | 0.25 | - | - | - | - |
| encounter-audit | 0.68 | 0.71 | 1.01 | 1.49 | 0.29 | - | - | - | - |
| ruff-gate | 0.58 | 0.67 | 0.74 | 1.27 | 0.27 | - | - | - | - |
| doctor-assets | 0.45 | 0.49 | 0.80 | 1.77 | 0.37 | - | - | - | - |
| mypy-island | 0.33 | 1.79 | 2.01 | 6.05 | 0.97 | - | - | - | - |
| runtime-player-smoke | 0.23 | 0.26 | 0.31 | 1.33 | 0.21 | - | - | - | - |

### windows: runner speed factor (median of 11 reference steps: doctor-assets, encounter-audit, exception-policy-scan, player-package-gate, pytest-fast, ruff-gate, runtime-player-smoke, swallow-scan-gate, verify-demo, verify-strict, web-smoke)

Speed factor over 24 runs: min 0.53, median 1.01, max 1.20; slowest/fastest 2.29; sd of log 0.222.

| step | corr with other steps' speed | slope | variance explained | sd log (raw) | sd log (residual) | residual drift corr | runner-adjusted growth, first to last run |
|---|---|---|---|---|---|---|---|
| doctor-assets | 0.97 | 1.80 | 0.94 | 0.400 | 0.094 | -0.17 | 0.948 |
| encounter-audit | 0.98 | 1.43 | 0.96 | 0.318 | 0.064 | -0.11 | 0.976 |
| exception-policy-scan | 0.83 | 0.62 | 0.70 | 0.184 | 0.102 | 0.32 | 1.113 |
| mypy-gate | 0.44 | 1.14 | 0.20 | 0.570 | 0.510 | -0.17 | 0.746 |
| player-package-gate | 0.99 | 0.86 | 0.98 | 0.217 | 0.031 | 0.04 | 1.004 |
| pytest-fast | 0.93 | 0.77 | 0.87 | 0.208 | 0.076 | 0.29 | 1.076 |
| ruff-gate | 0.96 | 1.34 | 0.92 | 0.307 | 0.086 | -0.05 | 0.986 |
| runtime-player-smoke | 0.98 | 0.89 | 0.96 | 0.224 | 0.043 | 0.07 | 1.009 |
| swallow-scan-gate | 0.91 | 0.76 | 0.83 | 0.205 | 0.085 | 0.11 | 1.032 |
| verify-demo | 0.97 | 1.41 | 0.95 | 0.318 | 0.074 | -0.02 | 0.995 |
| verify-strict | 0.96 | 1.27 | 0.93 | 0.290 | 0.076 | -0.07 | 0.982 |
| web-smoke | 0.98 | 0.73 | 0.96 | 0.188 | 0.036 | -0.15 | 0.983 |

Runs, slowest first (flagged = steps over the current thresholds):

| run | sha | event | speed | rank | flagged |
|---|---|---|---|---|---|
| 40509194015 | 1d2501d | push | 1.20 | 1 | exception-policy-scan, pytest-fast |
| 40537724584 | 4eb6667 | push | 1.11 | 2 | exception-policy-scan, pytest-fast |
| 40530270399 | 043d7b8 | push | 1.05 | 3 | exception-policy-scan, pytest-fast |
| 40502056355 | bf8bbd3 | pull_request | 1.04 | 4 | exception-policy-scan, pytest-fast |
| 40482657756 | ec51e36 | push | 1.04 | 5 | pytest-fast |
| 40537509580 | 49c2769 | push | 1.04 | 6 | pytest-fast |
| 40545138940 | 8613110 | push | 1.04 | 7 | exception-policy-scan, pytest-fast |
| 40530276385 | 043d7b8 | pull_request | 1.04 | 8 | exception-policy-scan, pytest-fast |
| 40537135746 | abdcf1c | pull_request | 1.03 | 9 | - |
| 40482662005 | ec51e36 | pull_request | 1.02 | 10 | - |
| 40540198141 | 0fbbef1 | push | 1.01 | 11 | - |
| 40502049562 | bf8bbd3 | push | 1.01 | 12 | pytest-fast |
| 40545051504 | 19a4c5d | push | 1.00 | 13 | pytest-fast |
| 40540237224 | 0fbbef1 | pull_request | 1.00 | 14 | pytest-fast |
| 40465949215 | 8216592 | push | 0.99 | 15 | pytest-fast |
| 40465951252 | 8216592 | pull_request | 0.85 | 16 | - |
| 40545149744 | 8613110 | pull_request | 0.82 | 17 | - |
| 40537734129 | 4eb6667 | pull_request | 0.76 | 18 | pytest-fast |
| 40480507815 | 75b8d8e | push | 0.75 | 19 | - |
| 40537523338 | 49c2769 | pull_request | 0.74 | 20 | - |
| 40537124494 | abdcf1c | push | 0.65 | 21 | - |
| 40509204836 | 1d2501d | pull_request | 0.62 | 22 | - |
| 40545056320 | 19a4c5d | pull_request | 0.58 | 23 | - |
| 40480510061 | 75b8d8e | pull_request | 0.53 | 24 | - |

Same commit, push vs pull_request (12 pairs): PR/push speed ratio median 0.82, range 0.51-1.57; correlation of the two runs' speed factors -0.03; PR slower in 2/12.

### windows: policies (k = 4.0; cross-validated over 24 post-opt runs)

Checked steps: current rule exception-policy-scan, player-package-gate, pytest-fast, verify-demo, web-smoke; other rules exception-policy-scan, mypy-gate, player-package-gate, pytest-fast, swallow-scan-gate, verify-demo, web-smoke. Detection = the regressed step itself is flagged. Uniform = every step x1.3; runner-like = every step x1.3**slope (the slopes in the speed table), i.e. the way the observed runners differ; both count runs with any step flagged.

| policy | false failures (runs) | uniform x1.3 fails | runner-like x1.3 fails | pytest-fast x1.25 | pytest-fast x1.5 | pytest-fast x2.0 | verify-demo x1.25 | verify-demo x1.5 | verify-demo x2.0 | mypy-gate x1.25 | mypy-gate x1.5 | mypy-gate x2.0 | exception-policy-scan x1.25 | exception-policy-scan x1.5 | exception-policy-scan x2.0 | swallow-scan-gate x1.25 | swallow-scan-gate x1.5 | swallow-scan-gate x2.0 | web-smoke x1.25 | web-smoke x1.5 | web-smoke x2.0 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a. current rule (committed budgets) | 13/24 (54%) | 22/24 (92%) | 19/24 (79%) | 79% | 92% | 100% | 62% | 62% | 83% | not checked | not checked | not checked | 79% | 96% | 100% | not checked | not checked | not checked | 12% | 62% | 88% |
| x. same-run total normalisation (unsafe) | 0/24 (0%) | 0/24 (0%) | 0/24 (0%) | 0% | 0% | 4% | 0% | 8% | 67% | 0% | 0% | 0% | 4% | 21% | 83% | 4% | 29% | 100% | 42% | 100% | 100% |
| b1. leave-one-out speed, unit slope | 0/24 (0%) | 0/24 (0%) | 0/24 (0%) | 8% | 46% | 100% | 0% | 25% | 96% | 0% | 0% | 0% | 4% | 12% | 79% | 8% | 33% | 100% | 17% | 83% | 100% |
| B. recommended: leave-one-out speed, fitted slope | 1/24 (4%) | 3/24 (12%) | 0/24 (0%) | 8% | 88% | 100% | 8% | 83% | 100% | 0% | 0% | 0% | 8% | 33% | 96% | 12% | 50% | 100% | 96% | 100% | 100% |
| A. advisory model (B as verify-all evaluates it) | 1/24 (4%) | 3/24 (12%) | 0/24 (0%) | 12% | 96% | 100% | 17% | 83% | 100% | 0% | 0% | 0% | 8% | 38% | 100% | 17% | 54% | 100% | 100% | 100% | 100% |
| b3. B + speed cap | 1/24 (4%) | 4/24 (17%) | 1/24 (4%) | 8% | 88% | 100% | 8% | 83% | 100% | 0% | 0% | 0% | 8% | 33% | 96% | 12% | 50% | 100% | 96% | 100% | 100% |
| c1. per-platform limit, k*sigma of log time | 0/24 (0%) | 1/24 (4%) | 0/24 (0%) | 0% | 0% | 17% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 4% | 25% | 0% | 4% | 17% | 0% | 0% | 50% |
| c2. per-platform limit, slowest/median + 0.10 | 1/24 (4%) | 16/24 (67%) | 15/24 (62%) | 54% | 71% | 92% | 42% | 62% | 79% | 17% | 17% | 29% | 4% | 25% | 92% | 4% | 25% | 79% | 62% | 79% | 96% |
| e. external calibration (job's full pytest) | 0/24 (0%) | 1/24 (4%) | 1/24 (4%) | 0% | 0% | 46% | 0% | 0% | 0% | 0% | 0% | 0% | 4% | 8% | 58% | 4% | 4% | 50% | 0% | 0% | 62% |
| f. a and A both (fixed ceiling and advisory) | 1/24 (4%) | 2/24 (8%) | 0/24 (0%) | 12% | 92% | 100% | 8% | 58% | 83% | 0% | 0% | 0% | 8% | 38% | 100% | 0% | 0% | 0% | 12% | 62% | 88% |

Historical runs each rule fails (cross-validated):

| policy | run | sha | event | flagged |
|---|---|---|---|---|
| a. current rule (committed budgets) | 40465949215 | 8216592 | push | pytest-fast |
| a. current rule (committed budgets) | 40482657756 | ec51e36 | push | pytest-fast |
| a. current rule (committed budgets) | 40502049562 | bf8bbd3 | push | pytest-fast |
| a. current rule (committed budgets) | 40502056355 | bf8bbd3 | pull_request | exception-policy-scan, pytest-fast |
| a. current rule (committed budgets) | 40509194015 | 1d2501d | push | exception-policy-scan, pytest-fast |
| a. current rule (committed budgets) | 40530270399 | 043d7b8 | push | exception-policy-scan, pytest-fast |
| a. current rule (committed budgets) | 40530276385 | 043d7b8 | pull_request | exception-policy-scan, pytest-fast |
| a. current rule (committed budgets) | 40537509580 | 49c2769 | push | pytest-fast |
| a. current rule (committed budgets) | 40537724584 | 4eb6667 | push | exception-policy-scan, pytest-fast |
| a. current rule (committed budgets) | 40537734129 | 4eb6667 | pull_request | pytest-fast |
| a. current rule (committed budgets) | 40540237224 | 0fbbef1 | pull_request | pytest-fast |
| a. current rule (committed budgets) | 40545051504 | 19a4c5d | push | pytest-fast |
| a. current rule (committed budgets) | 40545138940 | 8613110 | push | exception-policy-scan, pytest-fast |
| B. recommended: leave-one-out speed, fitted slope | 40537734129 | 4eb6667 | pull_request | pytest-fast |
| A. advisory model (B as verify-all evaluates it) | 40537734129 | 4eb6667 | pull_request | pytest-fast |
| b3. B + speed cap | 40537734129 | 4eb6667 | pull_request | pytest-fast |
| c2. per-platform limit, slowest/median + 0.10 | 40509194015 | 1d2501d | push | exception-policy-scan, swallow-scan-gate |
| f. a and A both (fixed ceiling and advisory) | 40537734129 | 4eb6667 | pull_request | pytest-fast |



### windows: uniform regressions via the rolling median of the run speed factor

Per-run speed sd of log 0.227 over 24 runs.

| window (runs) | rolling median speed, observed range | sd of log median (iid) | detectable uniform slowdown, 3 sd | 4 sd |
|---|---|---|---|---|
| 5 | 0.85-1.04 | 0.127 | 1.46 | 1.66 |
| 10 | 1.00-1.04 | 0.090 | 1.31 | 1.43 |
| 20 | 1.01-1.02 | 0.064 | 1.21 | 1.29 |

A persistent isolated regression, judged on the median of the runner-adjusted residuals of the last n runs (smallest factor above 4 sd):

| step | residual sigma | per run | median of 5 runs | median of 10 runs | median of 20 runs |
|---|---|---|---|---|---|
| pytest-fast | 0.079 | 1.37 | 1.19 | 1.13 | 1.09 |
| verify-demo | 0.077 | 1.36 | 1.19 | 1.13 | 1.09 |
| mypy-gate | 0.533 | 8.42 | 3.30 | 2.33 | 1.82 |
| exception-policy-scan | 0.106 | 1.53 | 1.27 | 1.18 | 1.13 |
| swallow-scan-gate | 0.089 | 1.43 | 1.22 | 1.15 | 1.11 |
| web-smoke | 0.037 | 1.16 | 1.09 | 1.06 | 1.04 |

### windows: re-run on failure (median job 13.9 min)

Repeating verify-all inside the same job would add about 3.0 min per run (sum of step medians) and cannot remove the runner-level part of the variance (the 'variance explained' column of the speed table).

| policy | first-attempt false failures | false failures after one re-run | extra job min per run | pytest-fast x1.25 (one try -> both tries) | pytest-fast x1.5 (one try -> both tries) | pytest-fast x2.0 (one try -> both tries) | exception-policy-scan x1.25 (one try -> both tries) | exception-policy-scan x1.5 (one try -> both tries) | exception-policy-scan x2.0 (one try -> both tries) | verify-demo x1.25 (one try -> both tries) | verify-demo x1.5 (one try -> both tries) | verify-demo x2.0 (one try -> both tries) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a. current rule | 13/24 (54%) | 28.3% | 7.52 | 79% -> 62% | 92% -> 84% | 100% -> 100% | 79% -> 62% | 96% -> 92% | 100% -> 100% | 62% -> 38% | 62% -> 38% | 83% -> 69% |
| B. recommended | 1/24 (4%) | 0.0% | 0.58 | 8% -> 0% | 88% -> 76% | 100% -> 100% | 8% -> 0% | 33% -> 10% | 96% -> 92% | 8% -> 0% | 83% -> 69% | 100% -> 100% |

### windows: recommended rule, sensitivity to k

| k | false failures | pytest-fast x1.25 | pytest-fast x1.5 | exception-policy-scan x1.25 | exception-policy-scan x1.5 | verify-demo x1.25 | verify-demo x1.5 | web-smoke x1.25 | web-smoke x1.5 |
|---|---|---|---|---|---|---|---|---|---|
| 3.0 | 2/24 (8%) | 29% | 100% | 17% | 71% | 42% | 100% | 100% | 100% |
| 3.5 | 1/24 (4%) | 17% | 96% | 8% | 46% | 29% | 92% | 100% | 100% |
| 4.0 | 1/24 (4%) | 8% | 88% | 8% | 33% | 8% | 83% | 96% | 100% |
| 4.5 | 0/24 (0%) | 4% | 46% | 8% | 17% | 4% | 75% | 88% | 100% |

### windows: recommended rule parameters (all post-opt runs)

| step | median s | slope b | residual sigma | allowed ratio over expectation | max speed seen (other steps) | current threshold/median |
|---|---|---|---|---|---|---|
| exception-policy-scan | 3.46 | 0.62 | 0.106 | 1.54 | 1.19 | 1.08 |
| mypy-gate | 17.08 | 1.14 | 0.533 | 8.80 | 1.20 | - |
| player-package-gate | 1.87 | 0.86 | 0.033 | 1.14 | 1.25 | 1.56 |
| pytest-fast | 124.66 | 0.77 | 0.079 | 1.38 | 1.27 | 0.98 |
| swallow-scan-gate | 3.83 | 0.76 | 0.089 | 1.44 | 1.19 | - |
| verify-demo | 21.82 | 1.41 | 0.077 | 1.37 | 1.27 | 1.18 |
| web-smoke | 5.40 | 0.73 | 0.037 | 1.16 | 1.27 | 1.32 |

## Either OS: 24 workflow runs with both jobs (regression injected into both)

| policy | workflow runs with a false failure | pytest-fast x1.25 | pytest-fast x1.5 | pytest-fast x2.0 | verify-demo x1.25 | verify-demo x1.5 | verify-demo x2.0 | mypy-gate x1.25 | mypy-gate x1.5 | mypy-gate x2.0 | exception-policy-scan x1.25 | exception-policy-scan x1.5 | exception-policy-scan x2.0 | swallow-scan-gate x1.25 | swallow-scan-gate x1.5 | swallow-scan-gate x2.0 | web-smoke x1.25 | web-smoke x1.5 | web-smoke x2.0 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a. current rule | 18/24 (75%) | 100% | 100% | 100% | 88% | 92% | 100% | 0% | 0% | 0% | 100% | 100% | 100% | 0% | 0% | 0% | 17% | 96% | 100% |
| B. recommended | 4/24 (17%) | 100% | 100% | 100% | 50% | 100% | 100% | 0% | 0% | 0% | 12% | 96% | 100% | 42% | 100% | 100% | 96% | 100% | 100% |
| A. advisory model | 4/24 (17%) | 100% | 100% | 100% | 58% | 100% | 100% | 0% | 0% | 0% | 12% | 96% | 100% | 54% | 100% | 100% | 100% | 100% | 100% |
