"""Scratch: the full dof_study (pictures + every check) with the samples' cap set to argv[1]. Usage: capstudy.py CAP PROJECT OUT [study args]"""
import sys
sys.path.insert(0, r"D:\Games\Mesh-dof")
sys.path.insert(0, r"D:\Games\Mesh-dof\tooling")
import engine.hd2d.dof as dof  # noqa: E402
dof.TAPS_MAX = int(sys.argv[1])
import dof_study  # noqa: E402
raise SystemExit(dof_study.main(sys.argv[2:]))
