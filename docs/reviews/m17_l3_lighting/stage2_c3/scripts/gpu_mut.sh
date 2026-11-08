S=/c/Users/slebb/AppData/Local/Temp/claude/c18a071c64bbe7a7/bff3a484-a7b8-4c6b-bf14-a015c42db67e/scratchpad/c3
until grep -q "^done" $S/gpu_suite.log 2>/dev/null; do sleep 20; done
cd /d/Games/Mesh-l3s
mut() {
  py -3.13 -c "import sys;p=sys.argv[1];s=open(p,encoding='utf-8').read();assert s.count(sys.argv[2])==1;open(p,'w',encoding='utf-8',newline='').write(s.replace(sys.argv[2],sys.argv[3]))" "$2" "$3" "$4" || { echo "$1: apply failed"; return; }
  r=$(GPU=1 BT=gm_$1 $S/run.sh -q tests/test_hd2d_lighting_controls_gpu.py 2>&1 | grep -E "^FAILED|passed|failed" | sed 's/ - .*//' | tr '\n' ' ')
  git checkout -q -- "$2"; echo "$1: $r"
}
mut placement_turns_2d_on engine/studio.py 'turn_on = not self.hd2d.active and not self._lit()' 'turn_on = not self._lit()'
mut shadows_write_2d_key engine/studio.py '        self._edit(lambda s: ops.set_hd2d_shadows(s, on), said)' '        self._edit(lambda s: ops.set_room_lighting(s, shadows="hard" if on else "none"), said)'
git status --short
echo mutdone
