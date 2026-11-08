#!/usr/bin/env bash
S=/c/Users/slebb/AppData/Local/Temp/claude/c18a071c64bbe7a7/bff3a484-a7b8-4c6b-bf14-a015c42db67e/scratchpad/e1
cd /d/Games/Mesh-l3e
GPU=1 bash $S/run.sh py -3.13 -m pytest -q -W error -p no:cacheprovider --basetemp="$(cygpath -w $S/tmp/g)" tests/*_gpu.py > $S/gpu_suite.log 2>&1
echo "gpu exit $?" >> $S/gpu_suite.log
bash $S/run.sh py -3.13 -m pytest -q -W error -p no:cacheprovider --basetemp="$(cygpath -w $S/tmp/a)" > $S/full_suite.log 2>&1
echo "full exit $?" >> $S/full_suite.log
