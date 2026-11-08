#!/usr/bin/env bash
# usage: run.sh <cmd...>  (in the worktree WT, default Mesh-l3e; scratch user folders)
S=/c/Users/slebb/AppData/Local/Temp/claude/c18a071c64bbe7a7/bff3a484-a7b8-4c6b-bf14-a015c42db67e/scratchpad/e1
export APPDATA="$(cygpath -w $S/env/appdata)" LOCALAPPDATA="$(cygpath -w $S/env/localappdata)" XDG_DATA_HOME="$(cygpath -w $S/env/xdg)"
export MESH_USER_DIR="$(cygpath -w $S/env/user)" MESH_PROJECTS_DIR="$(cygpath -w $S/env/projects)" MESH_STUDIO_NO_AI_BRIDGE=1
[ -n "$GPU" ] && export MESH_GL_SMOKE=1
cd /d/Games/${WT:-Mesh-l3e}
exec "$@"
