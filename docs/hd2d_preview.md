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

## Rivers and streams

A river is one continuous ribbon of water that flows downstream. Draw and edit rivers with **River**, under the
**Sculpt**, **Paint** and **Scatter** buttons in the 3D view's panel. The AI assistant and `mesh author` make the
same checked edits (`add_river`, `set_river`, `remove_river`).

- **Draw:** with River on and no river selected, click the ground where the river starts (upstream), then click
  downstream, one point at a time. The river is shown as you go, but nothing is saved until **Enter** (or
  **Finish**), which needs two points at least. **Esc** drops it.
- **New points:** a new point's water stands 0.25 m above the ground you click, never higher than the point before.
  New rivers are 2 m wide and flow at 1 m/s. Change these defaults under the River panel before you draw.
- **Edit:** click a river to select it, or a point's post to select that point.
  - Drag a post to move its point; its width and water level stay.
  - **Insert** adds a point after the selected one, halfway along the course.
  - **Delete** removes the selected point (a river keeps two at least) or, with no point selected, the river.
  - The panel sets the point's **Width** and **Water level**, and the river's **Flow**, **Waves** and **Reflection**.
  - **Reverse flow** turns the river round. Its water levels still fall from the new first point, so the water
    is relevelled where it stands: on a sloping river it rises at the old mouth and drops at the old source.
    Sculpt the bed to match, or set the points' water levels again.
- **One undo step each:** finishing a river, one drag, an insert, a removal and each value typed are one undo step
  each. Undo, room changes and **Play** drop a drag or a river still being drawn.
- **Refused edits change nothing:** a point, drag or value that the checks below refuse leaves the river as it was,
  and Mesh says why. While a drag is somewhere refused, the river stays at its last valid shape and a red post
  marks the mouse.

- **Points:** `[x, y, width, level]` in pixels (32 px = 1 m), listed from upstream to downstream. Their order is the
  way the water flows. The course curves smoothly through every point. Width and level change evenly between points.
  `level` is the water's surface, like an object's elevation, and it may stay level or fall downstream, never rise.
- **Look:** `flow` (m/s; 0 is still water), plus `colour`, `deep_colour`, `opacity`, `depth`, `waves`, `reflection`
  and `rain_ripples`, as for a pond. Rivers mirror what stands above them through the same frame copy as ponds, take
  the room's sun, lamps and shadows, and ring with its rain, though not under a roof or bridge. Walking through a
  river's shallows ripples it (below).
- **Its bed.** The water shows only where its level is above the ground. With the river selected, **Carve the
  bed** lowers the ground under it into a channel:
  - deepest in the middle, rising to meet the water at its edge;
  - a bank climbing from the water at a walkable slope until it meets the ground (up to 12 m out);
  - where its water stood above the ground beside it (a new river is drawn a little over the ground clicked), the
    water is lowered to just under that ground first, so it lies in its bed. The ground is checked on both sides,
    half a metre out, every quarter metre along the river, not only at its points, so a dip between two points is
    found too. Ground nearer a pond's or another river's water than its own isn't its bank and isn't checked, and a
    river flowing into a pond is never lowered below the pond's level. Carving again changes nothing; a neighbour
    carved afterwards can lower the ground the two share, and then the first sinks once more;
  - flowing into a pond, its bed eases over its last 1.5 m to the pond's own depth just inside the shore, and
    nothing is dug in the pond past its shore's edge: the pond's ground stays as it is;
  - **Bed depth** (m): empty for a quarter of the river's width (0.2 to 1.2 m), or one depth for the whole river.
    The AI can give a depth for each point; a shallow point makes a ford.
  - Carving only ever lowers the ground: carving again changes nothing, and ground already lower is kept. It is one
    undo step.
  - You can also sculpt the bed yourself with **Sculpt**. Where the bed is wider than the river, the river's
    straight edge shows.
- **Plants in the water.** Scatter strokes keep out of rivers' water (reeds may stand in the shallows). **Clear
  plants** takes away the scattered grass, flowers, bushes and rocks already standing in the selected river's water,
  as one undo step. Objects, characters and structures are never touched, and editing or removing a river never
  touches scatter.
- **Wading and deep water.** Characters wade through water up to half a metre deep: their steps ripple it and
  send a `water_step` event, as in a pond, with no change of speed. Deeper water stops them at its edge, as a ledge
  does. Depth is the water over the ground or floor under their feet, so a bridge's deck above the water stays
  dry and walkable.
- **Walking into it** (the River panel; the AI: `passable`, `wade_depth`). This decides where characters may go,
  whatever the water looks like or however deep its bed is carved:
  - **Auto** (the default, as before): waded up to half a metre deep;
  - **Wade**: waded up to the **Wade depth** you give (0.1 to 1.5 m, 1 m unless set);
  - **Block**: not entered at all.

  In every case a bridge's deck over the water stays dry. A character put somewhere it can't stand (a start point
  in deep water, a teleport) can still walk out the shallower way, never deeper: in blocked water, only outwards
  towards its nearest edge (never across it, nor along it), and never into water beyond it deeper than they may
  wade. Characters on a **FloorRoute** walk out: from blocked water the quickest way, towards its nearest edge; from
  deep water to the nearest place they can stand, trying the nearest in each direction. If there's no way out they
  stay put, and the log and a `stranded` event say so once; they look again every few seconds. A route point they can't reach
  is tried again after a second. A character whose feet box is too wide for the places it could stand (the
  template's person picture is 2.4 m wide) may be stranded where a narrower one would get out, and a sculpted hole
  too steep to climb holds anyone, water or not.
- **Ponds** have the same choice in their inspector, under **Walking into it**. **Auto** keeps their **Walk through
  it** setting. In a 3D room that walks its floors in 3D (one with sculpted ground, rivers, or models with
  floors), a pond that blocks (Block, or Auto with Walk through it off) blocks exactly where its water is drawn.
  With the sculpted ground as its shore, that is where water stands over the ground. Its outline is used, not the
  box round it, so there's no invisible wall around a lake, at its corners, or where a river flows in. The player
  and characters on a **FloorRoute** walk that way; other moving characters still meet the box.
  - These keep blocking by the box round the pond: a 2D room's pond, a pond in a flat 3D room with none of those,
    and a pond shown only when flags say (its flags hide the box).
  - A pond on a raised floor doesn't block the ground under it. A pond whose shore is the sculpted ground is the
    exception, as it is drawn: its water reaches down to that ground wherever its level is above it, however deep,
    so whatever lies under its level there is in its water. In a room without sculpted ground it is drawn, and
    walked, like any other pond.
  - **Wade** depth needs the sculpted ground as the pond's shore. On flat ground, or in a 2D room, there is no
    depth, so a Wade pond is simply walked through.
- **Refused, with the reason and where:** a bend too tight for the river's width (its inner bank would fold), banks
  that cross or come within a quarter metre of each other, water that would run uphill, points closer than a
  quarter metre, two rivers that cross or overlap, and a bank off the room's ground.
- **Into a pond or lake.** Put the river's last point in a pond's water, then turn on **Into the pond** (the AI:
  `mouth: "auto"`). The river and the pond then show as one water surface:
  - none of the river's water is drawn inside the pond, so there's no second layer;
  - the pond's bank, reeds and stones stop where the river comes in, and so does its edge across the river;
  - over its last 1.5 m before the shore, the river takes on the pond's colour, waves and glints, and its current
    eases out.

  The panel names the pond it joins. It is refused, with what to change, if:
  - no pond lies under its last point, or that pond has the older Simple pond or Simple puddle look (choose Natural
    pond, Stone pool or Muddy puddle), or it shows only when flags say;
  - its end isn't wholly in the pond, it crosses the pond's shore more than once, or it runs with a bank in the
    pond's water well before it turns in;
  - over its last 1.5 m before the shore and in the pond, its water isn't within 5 cm of the pond's. The refusal
    names the points to change.

  Turn **Into the pond** on before carving its bed: carved first, its bed runs on into the pond, and carving only
  lowers, so that channel stays (as deeper pond water, walked as the rest of the pond is).

  Nothing is moved or relevelled to make it fit. If a pond is moved later so the join no longer holds, the river
  is drawn with a free end and the panel says why. Walking, wading and plants follow what is drawn. In the pond it
  is the pond's water, and the pond's own steps ripple it. The river's carved channel stays deep water there, so
  characters can't walk down into it.
- **Its ends.** **Ends** sets how its free ends finish: **Square** (rivers made before this, and right where a river
  runs off the room's edge), **Round** (half circles at both ends), **Round at source** or **Round at end** (a river
  flowing into a pond has no free end there: Square or Round at source). A
  round end is drawn as a half circle, walked and wading as drawn, and **Carve the bed** makes a bowl to match. Carving
  only lowers, so a bed carved square before stays square at its corners: those corners stay as a shallow, dry
  edge of the bed.
- **Limits:** at most 16 rivers in a room, each at most 1,024 m long and 2,048 m together, and at most 8 flowing
  into ponds.

Not yet:
- rivers joining each other;
- waterfalls;
- swimming, or any way to cross deep water other than a bridge or a ford;
- wading sounds or slowing down;
- rivers in 2D rooms.

A square end is cut square. Its bed ends there too: past it, a bank climbs from the water's level.

## Wind and moving decoration

Under **Wind and motion** in the 3D view's panel:

- **Calm, Breeze, Strong, Gusty** set the room's wind; **m/s**, **Toward** (degrees the wind blows to: 0 east, 90
  north) and **Gusts** (0-1) fine-tune it. The rain, snow and leaves of the room fall in the same wind (an effect with
  its own wind keeps it).
- **Animation** turns the decoration's movement on or off. Grass, reeds and flowers sway the most, bushes a little,
  a tree's canopy slowly; gusts roll across the meadow in waves. Torches flicker, banners stream downwind,
  glowcaps glow in the dark, water drips from the dripping rock. Off, everything stands exactly as drawn.
- **Sway** (how far plants bend), **Wind** (how much the wind moves them) and **Speed** (how fast they flutter and
  frames turn). The view moves while you edit, as it will in play. Each change is one undo step.
- Scatter **Torch**, **Banner**, **Small tree**, **Glowcaps**, **Bellflowers** and **Dripping rock** with the Scatter
  brush ("One thing at a time..."); a small dense dab places one. The small tree blocks like the boulder. A torch's
  flame doesn't light its surroundings: put a lamp beside it for that.

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
- **Lamps in lamp posts.** A lamp placed in a lamp post's lantern lights the ground round it; that lamp post doesn't
  shadow it. A small model, at most 1 m across, that holds the lamp counts as its own fixture. Walls, buildings and
  everything else, however close, still cast its shadows. A light inside a larger model, such as a lantern built into a
  house model, is still blocked by that model: make the lantern a model of its own.
- **The world's edges.** The village's ground stops at the room's edge, and there is no distant scenery.
- **Not supported:** weather, particles, depth of field and other post-processing effects.
- **Not a web target.** HD-2D games are not exported to the web.
