#!/bin/bash
L=/c/Users/slebb/AppData/Local/Temp/claude/c18a071c64bbe7a7/bff3a484-a7b8-4c6b-bf14-a015c42db67e/scratchpad/lva
cd /d/Games/Mesh-lva
for which in base cand; do
  O=$L/l1/validate/$which; mkdir -p $O/env
  for v in APPDATA LOCALAPPDATA XDG_DATA_HOME MESH_USER_DIR MESH_PROJECTS_DIR; do mkdir -p $O/env/$v; export $v="$(cygpath -w $O/env/$v)"; done
  for phase in play reopen export; do
    echo "=== $which $phase $(date +%T)"
    timeout 1500 py -3.13 tooling/lakeside_village.py $phase "$(cygpath -w $L/l1/$which)" "$(cygpath -w $O)" > $O/$phase.log 2>&1 || echo "FAILED $which $phase (exit $?)"
  done
  timeout 600 py -3.13 $(cygpath -w $L/l1/transitions.py) "$(cygpath -w $L/l1/$which)" "$(cygpath -w $O/transitions.json)" > $O/transitions.log 2>&1 || echo "FAILED $which transitions"
done
echo "=== done $(date +%T)"
sha256sum $L/l1/cand/packs/core_regions/scenes/*.json $L/l1/base/packs/core_regions/scenes/*.json | sed 's|.*scratchpad/lva/||'
