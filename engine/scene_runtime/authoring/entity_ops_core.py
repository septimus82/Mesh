# ruff: noqa
# mypy: ignore-errors
from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Callable, Dict

import engine.optional_arcade as optional_arcade

from ...background_layers import parse_background_layers
from ..index_build import build_scene_index_from_sprites
from . import entity_ops_align as _align_helpers
from . import entity_ops_geometry as _geometry_helpers
from . import entity_ops_transform as _transform_helpers
from .entity_ops_parts.selection_ops import (
    debug_add_entity_payload,
    debug_move_entity_by_id,
)
from .entity_ops_parts.delete_ops import debug_remove_entity_by_id
from .entity_ops_parts.spawn_ops import (
    debug_duplicate_along_path,
    debug_duplicate_entities_by_ids,
    debug_duplicate_to_grid,
    debug_group_selection,
    debug_scatter_selection,
    debug_ungroup_selection,
)
from .entity_ops_parts.property_ops import (
    debug_add_behaviour,
    debug_add_tag,
    debug_batch_rename,
    debug_remove_behaviour,
    debug_remove_tag,
    debug_set_name,
    debug_set_names,
    debug_set_prefab_id,
    debug_toggle_tag,
)
from .entity_ops_parts.transform_ops import (
    debug_align_selection,
    debug_distribute_selection,
    debug_mirror_selection,
    debug_nudge_selection,
    debug_rotate_selection,
    debug_snap_to_grid,
)
from .entity_ops_parts.debug_ops import (
    _debug_config_entity_has_behaviour,
    _debug_config_mutate_for_behaviour,
    _debug_config_set_field_for_behaviour,
    debug_config_scene_transition_set_spawn_id,
    debug_config_scene_transition_set_target_scene,
    debug_config_set_game_state_add_forbid_flag,
    debug_config_set_game_state_add_require_flag,
    debug_config_set_game_state_set_flag_true,
    debug_config_set_game_state_set_toast,
    debug_config_triggerzone_set_radius,
    debug_config_triggerzone_set_zone_id,
)
from .entity_ops_parts._shared import (
    _anchor_value,
    _build_entity_index,
    _build_used_id_set,
    _collect_participants,
    _debug_iter_authoring_payloads,
    _debug_remove_sprite,
    _entity_bounds,
    _is_group_entity,
    _next_group_id,
    _next_group_name,
    _next_unique_dup_id,
    _snap_value,
    _sorted_dedup_ids,
    debug_apply_authored_scene_payload,
    debug_find_sprite_by_entity_id,
    get_authored_scene_payload,
)

if TYPE_CHECKING:
    from ...scene_controller import SceneController


# ---------------------------------------------------------------------------
# Private helpers ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“ shared scaffolding for debug_* authoring ops
# ---------------------------------------------------------------------------






























# ---------------------------------------------------------------------------
# Facade: Geometry wrappers
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# Facade: Align / Distribute constants + wrappers
# ---------------------------------------------------------------------------

_ALIGN_X_MODES = _align_helpers._ALIGN_X_MODES
_ALIGN_Y_MODES = _align_helpers._ALIGN_Y_MODES
_ALIGN_VALID_AXES = _align_helpers._ALIGN_VALID_AXES
_ALIGN_VALID_REFS = _align_helpers._ALIGN_VALID_REFS
_DISTRIBUTE_VALID_MODES = _align_helpers._DISTRIBUTE_VALID_MODES





# ---------------------------------------------------------------------------
# Facade: Transform constants + wrappers
# ---------------------------------------------------------------------------

_SNAP_VALID_AXES = _transform_helpers._SNAP_VALID_AXES
_SNAP_VALID_MODES = _transform_helpers._SNAP_VALID_MODES
_ROTATE_VALID_ABOUT = _transform_helpers._ROTATE_VALID_ABOUT
_MIRROR_VALID_AXES = _transform_helpers._MIRROR_VALID_AXES
_MIRROR_VALID_ABOUT = _transform_helpers._MIRROR_VALID_ABOUT











# ---------------------------------------------------------------------------
# Selection: Group / Ungroup
# ---------------------------------------------------------------------------













# ---------------------------------------------------------------------------
# Selection: Duplicate to Grid
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# Selection: Duplicate Along Path
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# Selection: Scatter
# ---------------------------------------------------------------------------















