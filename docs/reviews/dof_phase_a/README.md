# #460 Phase A: depth-of-field feasibility (EVIDENCE ONLY)

This branch (`evidence/460-dof-phase-a`) exists so CI's Mesa llvmpipe lanes (Windows and Ubuntu) can measure a
**prototype** depth-aware depth-of-field pass. It is never merged.

- `dof_pass.py`: the prototype pass. It reads the HD-2D renderer's own world colour and depth attachments, linearises
  depth into metres along the view axis, and applies a bounded "scatter-as-gather" blur from each pixel's circle of
  confusion.
- `dof_lab.py`: the scratch lab. It attaches the pass to one process's renderer instance, after the world is drawn and
  before fog, post-processing and the HUD. That is where a shipped pass would replace the renderer's final blit. The
  lab captures off / subtle / miniature / CoC pictures and measures GPU time, detail kept, HUD, motion, GL objects and
  resizes.
- `tests/test_dof_feasibility_gpu.py`: runs the lab on the HD-2D template in the gpu lane, records
  `measure.dof_phase_a` and keeps the lab's report as an artifact.

No production, editor, scene, shader-in-product, CI-policy or threshold change. Phase B and C need separate owner
authorisation.
