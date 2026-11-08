S=/c/Users/slebb/AppData/Local/Temp/claude/c18a071c64bbe7a7/bff3a484-a7b8-4c6b-bf14-a015c42db67e/scratchpad/c3
BT=full3 $S/run.sh -q tests > $S/full_suite.log 2>&1; echo "exit $?" >> $S/full_suite.log
: > $S/gpu_suite.log
for f in test_hd2d_lighting_controls_gpu test_hd2d_shadow_allocation_gpu test_hd2d_lamp_fixture_gpu test_hd2d_lighting_gpu test_hd2d_studio_gpu test_hd2d_room_studio_gpu test_hd2d_runtime_gpu test_hd2d_starter_gpu test_hd2d_floors_gpu test_hd2d_cutaway_gpu test_hd2d_lab_gpu test_hd2d_visual_standard_gpu test_fire_gpu test_campfire_interaction_gpu test_character_shadows_gpu test_shadow_compositing_gpu test_shadow_corners_gpu test_shadow_geometry_gpu test_lighting_layer_release_gpu test_studio_3d_selection_gpu test_studio_room_undo_save_gpu test_studio_workflow_polish_gpu test_studio_workspace_gpu test_studio_label_wrap_gpu test_dof_studio_gpu test_gameplay_viewport_hud_gpu test_new_game_isolation_gpu test_saved_world_gpu test_runtime_debugger_gpu test_interaction_debugger_gpu test_ai_playtest_gpu test_hd2d_room_expand_gpu test_hd2d_asset_pipeline_gpu test_studio_ai_write_set_gpu test_room_file_ownership_gpu; do
  r=$(GPU=1 BT=g_$f $S/run.sh -q tests/$f.py 2>&1 | tail -n 1); echo "tests/$f.py | $r" >> $S/gpu_suite.log
done
echo done >> $S/gpu_suite.log
