from __future__ import annotations

import inspect


def _assert_single_args_param(fn, *, name: str) -> None:
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    assert len(params) == 1, f"{name} signature changed: expected 1 param, got {sig}"
    assert params[0].name == "args", f"{name} signature changed: expected param name 'args', got {sig}"
    assert params[0].kind in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ), f"{name} signature changed: expected positional 'args', got {sig}"


def _assert_three_params(fn, *, name: str, expected_names: tuple[str, str, str]) -> None:
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    assert len(params) == 3, f"{name} signature changed: expected 3 params, got {sig}"
    got = tuple(p.name for p in params)
    assert got == expected_names, f"{name} signature changed: expected {expected_names}, got {got} ({sig})"


def test_cli_command_signatures_contract() -> None:
    # Scene tilemap commands (called by scripts and higher-level authoring commands).
    from mesh_cli.scene import tilemap as tilemap_cli

    for fn_name in (
        "_handle_scene_tilemap_add_layer",
        "_handle_scene_tilemap_remove_layer",
        "_handle_scene_tilemap_init",
        "_handle_scene_tilemap_resize",
        "_handle_scene_tilemap_fill_rect",
        "_handle_scene_tilemap_clear_rect",
        "_handle_scene_tilemap_paint",
        "_handle_scene_tilemap_flood_fill",
        "_handle_scene_tilemap_brush",
    ):
        fn = getattr(tilemap_cli, fn_name)
        _assert_single_args_param(fn, name=f"mesh_cli.scene.tilemap.{fn_name}")

    # Shared tilemap validator used across stamp/verify-all pipelines.
    _assert_three_params(
        tilemap_cli._tilemap_validate_scene_payload,
        name="mesh_cli.scene.tilemap._tilemap_validate_scene_payload",
        expected_names=("scene_path_display", "scene_path", "scene"),
    )

    # Stamp commands.
    from mesh_cli.scene import stamp as stamp_cli

    for fn_name in (
        "_handle_scene_stamp",
        "_handle_scene_stamp_report",
    ):
        fn = getattr(stamp_cli, fn_name)
        _assert_single_args_param(fn, name=f"mesh_cli.scene.stamp.{fn_name}")

    # Scene ops used by the top-level scene management commands and invoked by verify-all plumbing.
    from mesh_cli.scene import ops as scene_ops

    for fn_name in (
        "_handle_scene_create",
        "_handle_list_scenes",
        "_handle_validate_scene_file",
        "_handle_tidy_scene",
        "_handle_new_scene",
        "_handle_edit_scene",
    ):
        fn = getattr(scene_ops, fn_name)
        _assert_single_args_param(fn, name=f"mesh_cli.scene.ops.{fn_name}")

