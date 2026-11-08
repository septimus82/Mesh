#!/usr/bin/env bash
S=/c/Users/slebb/AppData/Local/Temp/claude/c18a071c64bbe7a7/bff3a484-a7b8-4c6b-bf14-a015c42db67e/scratchpad
GPU=1 WT=Mesh-l3g bash $S/e1/run.sh py -3.13 -m pytest -q -W error -p no:cacheprovider --basetemp="$(cygpath -w $S/e2/g)" tests/*_gpu.py > $S/e2/gpu_suite.log 2>&1
echo "gpu exit $?" >> $S/e2/gpu_suite.log
WT=Mesh-l3g bash $S/e1/run.sh py -3.13 -m pytest -q -W error -p no:cacheprovider --basetemp="$(cygpath -w $S/e2/a)" > $S/e2/full_suite.log 2>&1
echo "full exit $?" >> $S/e2/full_suite.log
