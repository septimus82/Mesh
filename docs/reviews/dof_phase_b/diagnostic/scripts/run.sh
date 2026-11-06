#!/bin/bash
S=$(cygpath -w /c/Users/slebb/AppData/Local/Temp/claude/c18a071c64bbe7a7/bff3a484-a7b8-4c6b-bf14-a015c42db67e/scratchpad/dofb)
cd /c/Users/slebb/AppData/Local/Temp/claude/c18a071c64bbe7a7/bff3a484-a7b8-4c6b-bf14-a015c42db67e/scratchpad/dofb/diag
for run in a b; do
  echo "=== $run $(date +%T)"
  timeout 1500 py -3.13 diag.py "$S/lakeside" "$S/diag/d_$run" 300 >/dev/null 2>"d_$run.err" || echo "FAILED $run"
done
echo "=== done $(date +%T)"; tasklist | grep -ci nvidia-smi
