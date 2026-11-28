# Rolling verify-all timing check (last 24 runs per OS; k = 4)

## linux: 24 runs, 2026-10-27T07:14:42Z to 2026-10-27T16:52:21Z

Median runner speed 1.112 (limit 1.206; fitted runs' range 0.622-1.152): ok.

| step | median observed/expected | limit | verdict |
|---|---|---|---|
| exception-policy-scan | 1.107 | 1.063 | PERSISTENT REGRESSION |
| player-package-gate | 0.983 | 1.032 | ok |
| pytest-fast | 1.151 | 1.036 | PERSISTENT REGRESSION |
| swallow-scan-gate | 1.063 | 1.053 | PERSISTENT REGRESSION |
| verify-demo | 0.984 | 1.071 | ok |
| web-smoke | 1.003 | 1.036 | ok |

## windows: 24 runs, 2026-10-27T07:14:42Z to 2026-10-27T16:52:21Z

Median runner speed 1.179 (limit 1.269; fitted runs' range 0.621-1.302): ok.

| step | median observed/expected | limit | verdict |
|---|---|---|---|
| exception-policy-scan | 1.135 | 1.086 | PERSISTENT REGRESSION |
| player-package-gate | 0.969 | 1.044 | ok |
| pytest-fast | 1.142 | 1.103 | PERSISTENT REGRESSION |
| swallow-scan-gate | 1.043 | 1.089 | ok |
| verify-demo | 0.981 | 1.085 | ok |
| web-smoke | 0.987 | 1.051 | ok |
