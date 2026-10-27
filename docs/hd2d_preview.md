# HD-2D RPG (Preview): creator help

**HD-2D RPG (Preview)** is an example project you can play and edit. It is a small 3D village with buildings,
pixel-art characters, stairs, a bridge you can cross or walk under, lamps and sunlight, people to talk to, a sign, and
a cottage you can walk into.

It is a **preview**. The 3D tools work and are tested, but some features are still experimental, and the art is
starter art rather than finished game art.

## Start a project

- **In the launcher:** start it with `Mesh Engine.bat` in the engine folder, or `python -m engine.launcher` with a
  pip-installed Mesh. Choose **New Project**, then **HD-2D RPG (Preview)**, give it a name and press
  **Create & Open**.
- **From a terminal:** `mesh new MyGame --template hd2d_rpg`, then `mesh edit` in its folder.

## The two cameras

- **Mesh Studio's camera** is free, for building:
  - Turn left/right, Tilt up/down, Reset view and Frame it;
  - middle-drag pans, the wheel zooms and WASD moves.
  It never changes your game.
- **The gameplay camera** is what the game uses when you press **Play (F4)**:
  - a long lens (12°) looking north at a fixed angle: 30° outdoors, 55° indoors;
  - it follows the player and never shows past the room's edges;
  - at 720 lines the art's 32 pixels per metre are drawn at exactly 2× outdoors and 3× indoors.

Studio has no controls for the gameplay camera yet. It is part of each room's settings (`settings.hd2d.camera`: pitch,
fov, distance, `ortho` for a flat orthographic look, and `bounds`).

## Models from Blender

Export each model from Blender 4 with **File > Export > glTF 2.0**:

| Setting | Value |
|---|---|
| Format | **glTF Binary (.glb)** (one file, textures embedded) |
| Include > Custom Properties | **On** (it carries collision) |
| Transform > +Y Up | On (the default) |
| Mesh > Apply Modifiers, UVs, Normals | On |
| Compression (Draco) | **Off** |
| Animation, armatures, shape keys | None: models are static |

**How Mesh reads a model:**

- **Scale and placement.** One Blender unit is one metre. The object's origin is where it stands, and Z = 0 is the
  ground.
- **Textures.** One base-colour PNG per material, or a flat colour.
- **Collision** is separate objects that Mesh never draws, each with the custom property `mesh_collision`:
  - `solid`: you can walk on top, and it blocks below;
  - `floor`: walkable on top and open underneath, like a bridge deck;
  - `wall`: blocks movement.

  Keep these objects' names the same between exports.

**Pixel textures:**

- Use 32 pixels per metre.
- In Blender, set each Image Texture node's interpolation to **Closest**.
- If you forget, leave **Keep pixels sharp** on (the default) when importing: Mesh fixes its copy so pixels stay
  crisp. Blender's default (Linear) blurs pixel art.

**Adding a model:**

1. Open **Models...** in Mesh Studio and use **Import 3D model**.
2. Type or browse to the `.glb` file. Mesh checks it and copies it into your project; your file is never changed.
3. Open the model's page and choose **Place in scene**, then click the ground.

**Changing a model:**

1. Export it again from Blender.
2. Use **Reimport** on its page. Every placed copy updates, and Mesh reports what changed (size, collision, floors).

Mesh doesn't watch your Blender files: reimporting is always your choice.

## Placing and editing

- **Structures:** click one to select it. Drag it to move it; use the inspector to turn it, raise it or set its
  position exactly.
- **People and signs:** choose **Person** or **Sign**, then click a floor in the 3D view. They stand on that floor
  (the ground, a hilltop or the bridge) at its height. A spot where nobody could stand is refused, and Mesh says why.
  Edit what someone says in the inspector's **Dialogue** tab.
- **Undo and save:** Ctrl+Z / Ctrl+Y undo and redo every edit; Ctrl+S saves.

## Shaping and painting the ground

In the 3D view's panel, **Sculpt**, **Paint** and **Scatter** turn a brush on. Hold the mouse on the ground and drag.
Each stroke is one change, so one Ctrl+Z undoes it, and Esc cancels a stroke before you let go.

- **Sculpt:** Raise, Lower, Smooth or Flatten. Shift lowers, Ctrl smooths, and Alt+click picks a height to flatten
  to. Sculpting never moves people or buildings: Mesh says what it left floating or buried, and **Settle on the
  ground** stands them back on it.
- **Paint:** Grass, Earth, Stone, Mud or Sand. Use Earth for paths, Mud for pond banks and Stone for
  rocky ground and cliffs. Shift paints grass back, and Alt+click picks the material under the mouse. Painting changes
  how the ground looks, never where anyone can walk.
- **Edges:** **Soft** borders wander a little, in crisp pixels, and show bare earth along cliff tops. **Hard** keeps
  borders exactly where you painted them.
- **Scatter:** grass, flowers, bushes, reeds, rocks and fallen branches, alone or in collections (Meadow, Wildflowers,
  Pond edge, Shrubs, Rocks, Deadfall). A stroke fills the ground it passes over up to the density, in clumps, only
  where the rules allow: the materials you switch on, no steeper than the slope, out of water (reeds may stand in the
  shallows) and off buildings. Shift removes what is under the brush, Ctrl thins it. Scattered things stand on the
  ground and rise and fall with it when you sculpt; Mesh says when some now stand where they wouldn't be put.
  Everything is walked through except the boulder, and Mesh says when one stands in a doorway, on someone's route or
  where the player starts. Less is often more: leave plain ground around paths and buildings.
- `[` and `]` change the brush's size.

## Seeing through buildings (cutaway)

A building can hide the player who walks behind or into it. Select the building and switch on
**See-through in play**. In play, the part of that building between the camera and the player is then not drawn, so
the player stays in view.

- Walls, collision and shadows stay as they are.
- Leave it off for bridges and hills: their cover is meant to be seen.
- The template's cottage and shop have it on.

## Sharing your game

`mesh export build`, run in your project's folder, writes your game to `dist/bundle`: its rooms, models, art and
sounds, plus Mesh's engine.

- **It is not a standalone program.** The person playing needs **Python 3.11 or newer** with Mesh's dependencies:
  `pip install "arcade>=3,<4" "pillow>=10,<12" "jsonschema>=4,<5"`.
- **To play it:** `python main.py` in that folder.
- **No executable:** Mesh doesn't make an `.exe` or an installer.

## Known limitations

- **Models are static.** There are no animated 3D characters: characters are pixel-art sprites that face the camera.
- **No automatic Blender sync.** Reimport is manual.
- **No gameplay camera controls in Studio yet** (above). Studio's own camera is separate and free.
- **Hidden areas:**
  - the see-through opening has a hard edge;
  - only the player is revealed, not other characters behind a building;
  - a building's wall nearest the camera can still hide part of a small room.
- **Character lighting.** Characters take light from the sun and lamps, but their shading is drawn into the art; a
  lamp doesn't light them from one side.
- **The world's edges.** The village's ground stops at the room's edge, and there is no distant scenery.
- **Not supported:** weather, particles, depth of field and other post-processing effects.
- **Not a web target.** HD-2D games are not exported to the web.
