import json, glob, sys, os
B = sys.argv[1]
for f in sorted(glob.glob(B + r'\n_*\packs\core_regions\scenes\*.json')) + sorted(glob.glob(B + r'\n_*\assets\prefabs.json')):
    d = json.load(open(f, encoding='utf-8'))
    ents = d.get('entities', []) if isinstance(d, dict) else [p.get('entity', {}) for p in d]
    print(os.path.relpath(f, B), [(e.get('name') or e.get('id'), e.get('tag'), e.get('behaviours'), e.get('x'), e.get('y')) for e in ents][:14])
