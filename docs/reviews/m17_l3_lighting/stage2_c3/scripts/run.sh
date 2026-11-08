#!/usr/bin/env bash
# usage: run.sh <pytest args...>   (env: GPU=1 for MESH_GL_SMOKE)
S=/c/Users/slebb/AppData/Local/Temp/claude/c18a071c64bbe7a7/bff3a484-a7b8-4c6b-bf14-a015c42db67e/scratchpad/c3
export APPDATA="$(cygpath -w $S/env/appdata)" LOCALAPPDATA="$(cygpath -w $S/env/localappdata)" XDG_DATA_HOME="$(cygpath -w $S/env/xdg)"
export MESH_USER_DIR="$(cygpath -w $S/env/user)" MESH_PROJECTS_DIR="$(cygpath -w $S/env/projects)"
[ -n "$GPU" ] && export MESH_GL_SMOKE=1
cd /d/Games/Mesh-l3s
exec ${PY:-py -3.13} -m pytest -W error -p no:cacheprovider --basetemp="$(cygpath -w $S/tmp/${BT:-bt})" "$@"
