# Godot Engine — Repository Survey & Research Notes

*Generated 2026-09-25 from a full read-through of `/home/user/godot` plus upstream research.*

---

## 1. What this repository is

| | |
|---|---|
| Project | **Godot Engine** — free, MIT-licensed, cross-platform 2D/3D game engine |
| Version | **4.8-dev** (`version.py`: major 4, minor 8, patch 0, status `dev`) |
| Last stable | **4.7**, released 2026-06-18 (per `CHANGELOG.md`) |
| 4.8 target | Q4 2026 (estimate, per Godot release policy) |
| Remote | `https://github.com/shakil603/godot.git` — a **fork** of `godotengine/godot` |
| Branch | `arena/01a0d682-godot`, off `30caae98b79ec7e75e5f893290a51b4048eaa141` |
| HEAD | `30caae98` — *Merge PR #123525 (web editor download sources)*, Thaddeus Crews, **2026-09-24** |
| Freshness | `git ls-remote` on upstream `master` returns the **identical SHA** → this tree is exactly current with upstream as of yesterday |
| History | **Shallow clone, depth 1** (`.git/shallow` present) — `git log`, `blame`, and `FROM_REF` diff logic all have no history to work with |
| Size | 429 MB on disk, **14,385 tracked files** |
| License | MIT (`LICENSE.txt`), contributors in `AUTHORS.md`, third-party notices in `COPYRIGHT.txt` (~100 KB) |

### Scale by the numbers

Engine code (excluding `thirdparty/`): **~1.67 M lines**

| Layer | Lines | Files |
|---|---|---|
| `modules/` | 352,804 | 987 |
| `scene/` | 331,794 | 727 |
| `editor/` | 320,060 | 640 |
| `servers/` | 183,767 | 400 |
| `core/` | 174,220 | 443 |
| `platform/` | 112,926 | 302 |
| `drivers/` | 107,718 | 169 |
| `tests/` | 75,446 | 186 |
| `main/` | 7,242 | 9 |
| `thirdparty/` | 3,116,483 | — (70 vendored libraries) |

---

## 2. Architectural layering

Godot is strictly layered; dependencies point downward only.

```
        ┌─────────────────────────────────────────────┐
        │  main/          bootstrap, Main::iteration()│
        ├─────────────────────────────────────────────┤
        │  editor/        the IDE (only in `editor`   │
        │                 target; stripped from       │
        │                 template builds)            │
        ├─────────────────────────────────────────────┤
        │  modules/       60 optional, toggleable     │
        │                 features (GDScript, C#,     │
        │                 Jolt, glTF, OpenXR, …)      │
        ├─────────────────────────────────────────────┤
        │  scene/         the Node/SceneTree system,  │
        │                 2D, 3D, GUI, animation      │
        ├─────────────────────────────────────────────┤
        │  servers/       abstract singletons behind  │
        │                 RIDs: Rendering, Physics2D/ │
        │                 3D, Audio, Navigation, XR,  │
        │                 Text, Display, Camera       │
        ├─────────────────────────────────────────────┤
        │  drivers/       concrete backends: Vulkan,  │
        │                 D3D12, Metal, GLES3, SDL3,  │
        │                 AccessKit, audio, PNG       │
        ├─────────────────────────────────────────────┤
        │  core/          Object, ClassDB, Variant,   │
        │                 containers, math, IO, OS    │
        └─────────────────────────────────────────────┘
              platform/  (android, ios, linuxbsd, macos,
                          visionos, web, windows)
```

### 2.1 `core/` — the object model

* **`Object`** (`core/object/object.cpp`, 79 KB / `object.h`, 48 KB) — root of everything.
  Not ref-counted by default; `RefCounted` adds it.
* **`ObjectID`** — a 64-bit handle; **bit 63 marks "is RefCounted"**, which is how the engine
  detects dangling-reference errors at runtime.
* **`ObjectDB`** — global registry of live objects, used for leak reporting at shutdown.
* **`ClassDB`** (`class_db.cpp`, 72 KB) — the reflection database: classes, methods,
  properties, signals, enums, constants, inheritance. Every `GDCLASS` macro registers here.
* **`GDType`** (`core/object/gdtype.h|cpp`) — **newer, hot code**. A per-type "unified member map"
  holding properties, methods, signals, integer constants and enums in one `AHashMap<StringName, Member>`
  (tagged union payload). Upstream notes: *"Move property maps from ClassDB to GDType.
  Accelerate Object property access 1.6×"* (GH-122596) and *"Simplify GDType by storing all
  properties in a single unified map. Save ~12 MB runtime RAM"* (GH-122751).
  `InitState {UNINITIALIZED, MUTABLE, FINALIZED}` guards mutation after startup.
* **`MethodBind` / `method_bind_common.h`** — templated trampolines turning C++ member
  functions into the `Variant **args` calling convention.
* **`Variant`** (`core/variant/`) — the universal value type. ~40 variants: NIL, BOOL, INT,
  FLOAT, STRING, the math types (Vector2/3/4(+i), Rect2, Transform2D/3D, Plane, Quaternion,
  AABB, Basis, Projection), COLOR, STRING_NAME, NODE_PATH, RID, OBJECT, CALLABLE, SIGNAL,
  DICTIONARY, ARRAY, plus 10 packed arrays. `variant_call.cpp` is the giant dispatch table.
* **`core/templates/`** — hand-rolled containers: `Vector` (CoW), `LocalVector`, `AHashMap`,
  `HashMap`, `RBMap`, `List`, `SelfList`, `RingBuffer`, `PagedAllocator`, `RID_Owner`,
  `SafeList`, `FixedVector`, `Span`, `LRU`, `BVH` (in `core/math/bvh*`, split across
  many `.inc` files).
* **`core/io/`** — `FileAccess` (plus compressed/encrypted/pack/patched/zip/memory variants),
  `ResourceLoader`/`ResourceSaver`, binary & text resource formats, `ResourceUID`,
  `JSON`, `XMLParser`, sockets/TLS/DTLS, `Image` + loaders.
* **`core/math/`** — full geometric math library, A*, Delaunay 2D/3D, quickhull, convex hull,
  `Expression` (runtime expression evaluator), `RandomPCG`, `DynamicBVH`, triangulation.
* **`core/extension/`** — **GDExtension**, the C ABI for native plugins (see §5).

### 2.2 `servers/` — the abstraction layer

Servers are singletons that own resources addressed by `RID`. Scene-layer nodes are thin
front-ends that push state into a server. This decoupling allows headless operation
(`servers/rendering/dummy/`) and multithreaded wrapping (`server_wrap_mt_common.h`,
`RenderingServerDefault`).

* `servers/rendering/` — `RenderingServer` (10 K-line public API), `RendererCompositor`,
  `RendererViewport`, `RendererSceneCull`, `RendererCanvasCull`, occlusion culling,
  light culling, the whole **shader toolchain** (`shader_language.cpp` is 12,328 lines —
  the GDShader parser/compiler; `shader_preprocessor.cpp`, `shader_compiler.cpp`,
  `shader_warnings.cpp`, `shader_include_db.cpp`).
* **`RenderingDevice`** (`rendering_device.cpp`, 10,541 lines) — Godot's modern
  GPU-abstraction: buffers, textures, samplers, uniform sets, pipelines, compute/draw/
  **ray-tracing** lists, and a **render graph** (`rendering_device_graph.h|cpp`) that
  records instructions, computes dependencies and inserts barriers automatically.
  `USE_BUFFER_BARRIERS` is on, with a comment noting they exist mostly to work around
  driver bugs (ref PR #84976).
* Renderers under `renderer_rd/`: **`forward_clustered`** (desktop Forward+),
  **`forward_mobile`**, plus `effects/`, `environment/`, `storage_rd/`,
  `pipeline_cache_rd`, `framebuffer_cache_rd`, `uniform_set_cache_rd`, `cluster_builder_rd`.
* `servers/physics_2d|3d`, `navigation_2d|3d`, `audio`, `text`, `xr`, `display`,
  `camera`, `movie_writer`, `debugger`.

### 2.3 `scene/` — nodes

* `scene/main/`: `Node`, `SceneTree`, `Viewport`, `Window`, `CanvasItem`, `CanvasLayer`,
  `Timer`, `MultiplayerAPI`, `HTTPRequest`.
* **`scene_tree_fti.cpp|h`** — *Fixed-Timestep Interpolation*, the modern replacement for
  classic physics interpolation. Notable engineering: raw pointers + explicit delete
  notification, a **48-deep scene-tree depth limit**, three traversal modes
  (`TM_DEFAULT`, `TM_LEGACY`, `TM_DEBUG`) and a compile-time
  `GODOT_SCENE_TREE_FTI_VERIFY` self-check. Has its own unit test file
  (`scene_tree_fti_tests.cpp`). Stubbed out entirely under `_3D_DISABLED`.
* `scene/2d/` — Sprite2D, AnimatedSprite2D, Camera2D, TileMap (module), lights & occluders,
  GPU/CPU particles, Parallax2D, Line2D, Polygon2D, Skeleton2D, physics bodies.
* `scene/3d/` — a **very** large surface: MeshInstance3D, lights, decals, fog volumes,
  GI (LightmapGI, VoxelGI, ReflectionProbe, OccluderInstance3D), particles, and an
  extensive **skeleton/IK/bone-modifier** suite: `Skeleton3D`, `SkeletonModifier3D`,
  FABRIK, CCD-IK, Two-Bone-IK, Spline-IK, Jacobian-IK, Iterate-IK, Chain-IK,
  LookAt/Aim/CopyTransform/ConvertTransform/Retarget/IkModifier3D,
  `BoneSpaceAdjuster3D` (renamed from BoneSpreader3D in dev5), `BoneTwistDisperser3D`,
  `BoneConstraint3D`, and `SpringBoneSimulator3D` + sphere/capsule/plane collisions.
  **`Trail3D`** (987 lines, new in 4.8 dev4) and **`Line3D`** (54 lines — declared but
  effectively **unimplemented**, matching upstream's note that only enums exist).
* `scene/gui/` — the Control system: `TextEdit` (10,161 lines, the single largest scene file),
  `RichTextLabel` (8,684), `Tree` (7,782), plus CodeEdit, GraphEdit, etc.
* `scene/animation/`, `scene/resources/`, `scene/theme/`, `scene/audio/`.

### 2.4 `editor/` — the IDE

320 K lines, built **only** for `target=editor`; export templates strip it entirely.

* `editor_node.cpp` (9,871 lines) — the application shell.
* `editor_main_screen.cpp|h` — **dockified in 4.8**: main screens are no longer tied to
  plugins; they are regular `EditorDock`s in a `DockTabContainer`. A
  `LegacyMainScreenContainer` survives under `#ifndef DISABLE_DEPRECATED`.
* `editor/docks/` — `EditorDock`, `EditorDockManager`, `DockTabContainer`, plus
  FileSystem / SceneTree / Inspector / Import / Signals / Groups / History docks.
  `EditorDock` has 13 `DockSlot`s, 4 layout bits (vertical/horizontal/floating/main-screen),
  per-dock shortcuts, and virtual `_save_layout_to_config` hooks.
* Other areas: `inspector/`, `import/`, `export/`, `script/`, `shader/`, `animation/`
  (`animation_track_editor.cpp`, 10,056 lines), `debugger/`, `asset_library/`,
  `project_manager/`, `project_upgrade/`, `version_control/`, `plugins/`
  (`EditorPlugin` base, only 12 files here — actual editors live in `editor/scene/`,
  `editor/animation/`, etc.), `themes/`, `translations/`, **1,041 SVG icons**.

### 2.5 `drivers/` — backends

| Category | Drivers |
|---|---|
| Rendering | `vulkan/` (7,564-line device driver), `d3d12/`, `metal/` (+ `metal3` variant), `gles3/`, `egl/`, `gl_context/` |
| Input | `sdl/` (**SDL3** joypad), platform-native |
| Accessibility | `accesskit/` → `AccessibilityServer` (screen-reader support, enabled by default) |
| Audio | `alsa`, `pulseaudio`, `coreaudio`, `wasapi`, `xaudio2`, MIDI (`alsamidi`, `coremidi`, `winmidi`) |
| Image | `png/` (libpng) |
| Platform glue | `unix/`, `windows/`, `apple/`, `apple_embedded/`, `backtrace/` |

Ray tracing is implemented in **Vulkan** (7 refs, `VkPhysicalDeviceAccelerationStructureFeaturesKHR`)
and **D3D12** (5 refs, DXR + a NIR bridge for Mesa/`godot_nir`), but **not in Metal** (0 refs).

### 2.6 `platform/` — OS ports

`android` (Java + Kotlin + Gradle), `ios`, `macos` (Objective-C++), `linuxbsd`
(X11 7,644-line display server + Wayland), `windows` (`display_server_windows.cpp`,
8,661 lines), `visionos`, `web` (Emscripten; JS engine wrapper, ESLint-configured,
`package.json`, MessagePort-based remote debugger, a `platform/web/editor/` for the
**web editor** — the subject of the HEAD commit).

---

## 3. The main loop (`main/main.cpp`, 5,386 lines)

Startup is split across `Main::setup()` (line 974, command-line & project settings),
`Main::setup2()` (line 3041, servers & boot logo), `Main::start()`, and
`Main::cleanup()` (line 5216).

`Main::iteration()` (line 4917) is the frame. Order matters:

1. Read ticks; `MainTimerSync::advance()` computes `process_step`, `physics_steps`,
   and `interpolation_fraction`.
2. Clamp `physics_steps` to `max_physics_steps_per_frame` (spiral-of-death guard).
3. `XRServer::_process()`.
4. **For each physics step:**
   agile input flush → `MainLoop::iteration_prepare()` (**FTI nodes prepared *before*
   the physics server moves them**, otherwise previous == current and interpolation
   silently no-ops) → `PhysicsServer3D::sync()` + `flush_queries()` → same for 2D →
   `MainLoop::physics_process()` → `NavigationServer2D/3D::physics_process()` →
   `MessageQueue::flush()` → `PhysicsServer::end_sync()` + `step()` → flush →
   `MainLoop::iteration_end()`.
5. `MainLoop::process(process_step * time_scale)`.
6. Rendering, idle, frame pacing, profiling counters.

Every stage is wrapped in `GodotProfileZone` / `GodotProfileZoneGrouped` macros
(Perfetto-compatible; `misc/scripts/install_perfetto.py`, SCons `profiler`/`profiler_path`).

---

## 4. Build system

**SCons** (≥ 4.4) + **Python ≥ 3.9**, C++17 (`/std:c++17` on MSVC), optional **ninja**
backend, optional **SCU** (single-compilation-unit) builds via `scu_builders.py`.

Helper Python: `methods.py` (65 KB), `platform_methods.py`, `gles3_builders.py`,
`glsl_builders.py` (GLSL → SPIR-V/reflection codegen), `core_builders.py`,
`main_builders.py`, `editor_builders.py`, `template_builders.py`, `modules_builders.py`.
`SConstruct` loads them through an explicit `_helper_module()` shim to avoid name clashes.

### Key options (`scons help`)
* `platform` = android/ios/linuxbsd/macos/visionos/web/windows
* `target` = **editor | template_release | template_debug**
* `arch` (auto/x86_32/x86_64/arm32/arm64/rv64/ppc32/ppc64/wasm32), `dev_build`,
  `optimize`, `debug_symbols`, `lto` (none/auto/thin/full), `production`
* Renderers: `rendering_device`, `forward_plus_renderer`, `forward_mobile_renderer`,
  `vulkan`, `opengl3`, `d3d12`, `metal` (Apple arm64 only), `use_volk`, `angle`
* `accesskit`, `sdl`, `xaudio2`, `minizip`, `brotli`, `precision` (single/double)
* **Granular feature stripping** → `_2D_DISABLED`, `_3D_DISABLED`, `ADVANCED_GUI_DISABLED`,
  `PHYSICS_2D_DISABLED`, `PHYSICS_3D_DISABLED`, `NAVIGATION_2D_DISABLED`,
  `NAVIGATION_3D_DISABLED`, `XR_DISABLED`, `DISABLE_DEPRECATED`
* `tests`, `compiledb` (for clangd), `vsproj`, `ninja`, `fast_unsafe`,
  `warnings` (extra/all/moderate/no), `werror`, `module_*_enabled=no` per module

### 60 modules
astcenc, basis_universal, bcdec, betsy, bmp, camera, csg, cvtt, dds, enet, etcpak, fbx,
freetype, **gdscript**, glslang, gltf, godot_physics_2d, godot_physics_3d, gridmap, hdr,
**interactive_music**, **jolt_physics**, jpg, jsonrpc, ktx, lightmapper_rd, mbedtls,
meshoptimizer, mobile_vr, **mono** (C#), mp3, msdfgen, multiplayer, navigation_2d,
navigation_3d, noise, objectdb_profiler, ogg, openxr, raycast (Embree), svg,
text_server_adv, text_server_fb, **texture_streaming** (new, dev5), tga, theora, tilemap,
tinyexr, upnp, vhacd, visionos_xr, visual_shader, vorbis, webp, webrtc, websocket, webxr,
xatlas_unwrap, zip.

---

## 5. GDExtension & the compatibility machinery

* `core/extension/gdextension_interface.json` — **179 interface functions, 147 types**,
  schema-validated in CI (`check-jsonschema`). Each entry carries a `since` version
  (136 from 4.1, then 4.2–4.7) and an optional `deprecated` block.
  **19 functions are currently deprecated**, e.g. `classdb_register_extension_class[2-5]`
  → `classdb_register_extension_class6`, `mem_alloc/realloc/free` → `*2`,
  `script_instance_create[2]` → `script_instance_create3`,
  `get_godot_version` → `get_godot_version2`.
* Header + dumper generated by `make_interface_header.py` / `make_interface_dumper.py`.
* `gdextension_special_compat_hashes.cpp` (**1,032 lines**) — a hand-maintained table of
  *old-hash → new-hash* pairs so that GDExtensions compiled against older engines keep
  resolving renamed/re-signatured methods (`add_point`, `play`, `draw_arc`, …).
* **79 `*.compat.inc` files** across the tree. Pattern: inside `#ifndef DISABLE_DEPRECATED`,
  define `_foo_bind_compat_<PR number>()` shims and a `_bind_compatibility_methods()`
  that re-registers the old signature. Building with `deprecated=no` deletes all of it.
* `misc/extension_api_validation/` + `misc/scripts/validate_extension_api.sh` — CI gate
  that fails on accidental GDExtension ABI breaks.
* `tests/compatibility_test/` — a standalone C GDExtension (`compat_checker.c`) with its
  own SConstruct, used to prove the interface header compiles and loads.
* `libgodot.h` / `godot_instance.cpp` — the embeddable-library entry point.

---

## 6. Scripting

* **GDScript** (`modules/gdscript/`, 52,310 lines). Classic pipeline:
  `gdscript_tokenizer` (text + `tokenizer_buffer` for exported bytecode) →
  `gdscript_parser` → `gdscript_analyzer` (type inference & errors) → `gdscript_linter`
  (warnings) → `gdscript_byte_codegen` → `gdscript_vm.cpp` (**4,037 lines, 105 opcodes**).
  Plus `gdscript_cache`, `gdscript_lambda_callable`, `gdscript_utility_functions`,
  a **language server** (`language_server/`, LSP — tested in `tests/test_lsp.h`) and its
  own `tests/` and `doc_classes/`. `modules/gdscript/README.md` is an excellent
  architecture write-up.
* **C# / .NET** (`modules/mono/`) — `csharp_script.cpp`, `mono_gd/` interop shims,
  GC handle management, `managed_callable`, `signal_awaiter_utils`, generated **glue**,
  `class_db_api_json` (dumps the API for the C# source generators), MSBuild props/targets,
  `global.json`. CI has a dedicated ".NET source generators tests" step.
* **GDExtension** for everything else; `script_language_extension.cpp` (37 KB) lets an
  extension implement a whole new language.

---

## 7. Tests

* Framework: **doctest** (`thirdparty/doctest/`), driven by `tests/test_main.cpp`,
  built only with `tests=yes`; run as `godot --test` (CI: linux_builds.yml line 240).
* **236 files in `tests/`**, **1,565** including `modules/*/tests`.
  **1,335 `TEST_CASE(`** occurrences; 10 named suites
  (`[ClassDB]`, `[Modules][GDScript]`, `[Modules][GDScript][Completion]`,
  `[Modules][GDScript][LSP][Editor]`, `[Navigation2D]`, `[Navigation3D]`,
  `[TextServer]`, `[Triangle2]`, `[PlaceholderScriptInstance]`, `Validate tests`).
* `tests/core/{config,crypto,input,io,math,object,os,string,templates,threads,variant}`,
  `tests/scene/` (`test_text_edit.cpp` is 8,411 lines), `tests/servers/`.
* Support: `display_server_mock.cpp`, `signal_watcher.h`, `test_macros.h`,
  `tests/create_test.py` scaffolding generator, `tests/data/` fixtures
  (endian binaries, images, fuzzy-search corpora, line-ending samples).
* `tests/python_build/validate_builders.py` — tests the *build system itself*.
  ✅ **Ran it here: clean.**

---

## 8. Documentation

* `doc/classes/` — **833 XML** class-reference files; `doc/class.xsd` schema;
  `doc/tools/make_rst.py` converts to Sphinx RST for <https://docs.godotengine.org>;
  `doc/tools/doc_status.py` reports completeness.
* ✅ **Ran `doc_status.py` here:** **1,112 documented classes**, 10,477/10,936 methods,
  6,000/6,101 constants, 6,962/7,032 members, 713/714 theme items, 517/518 signals,
  353/353 operators, 154/154 constructors → **97 % overall**.
  (Known gaps concentrate in `*Extension` classes, e.g. `XRInterfaceExtension` 35/39.)
* `doc/translations/` — 11 `.po` files (ca, es, fr, ga, it, ko, ru, ta, …); editor UI
  strings live in `editor/translations/` and are managed on Weblate.
* `doc/Doxyfile` + `doc/Makefile` for C++ API docs.

---

## 9. CI, style and governance

* **Two-stage pipeline.** `.github/workflows/runner.yml` (named "🔗 GHA") runs
  `static_checks.yml` **first**, and only fans out to the six platform build workflows
  (`android/ios/linux/macos/windows/web`) if `sources-changed == 'true'` or it isn't a PR.
  `changed_files.yml` declares exactly which globs count as "sources" (and a separate,
  heavily-excluded list for clangd/clang-tidy).
* **Static checks:** `prek` (a pre-commit runner) over `.pre-commit-config.yaml`:
  * clang-format **v22.1.5** for C/ObjC/Java **and a separate GLSL style**
    (`misc/utility/clang_format_glsl.yml`)
  * clang-tidy **22.1.7** — *manual stage only*, needs `compile_commands.json`
  * ruff check + ruff format, mypy 1.19.1, codespell 2.4.2, check-jsonschema
  * `make-rst` (dry-run), `doc-status`, `validate-builders`, shebang checks
* **Formatting rules** (`.clang-format`, LLVM base): **tabs, width 4**, `ColumnLimit: 0`
  (no hard wrap), `InsertBraces: true`, `AlignTrailingComments: Never`,
  parameters prefixed `p_` / returns `r_` (enforced by `.clang-tidy`
  `readability-identifier-naming`), and a **6-tier include regrouping order**:
  `*.compat.inc` → own header → engine dirs → modules/platform → thirdparty →
  system (`windows.h`, Jolt, `platform_gl.h` pinned near-last).
* `.editorconfig`: UTF-8, LF, tabs (spaces for `.py`/SCons/YAML), final newline,
  120-col guidance.
* `pyproject.toml`: ruff (line-length 120, preview mode, isort with a custom
  `metadata` section for `misc.utility.scons_hints`), mypy strict-ish on Python 3.9,
  codespell with a long curated `ignore-words-list`.
* **Ownership:** `.github/CODEOWNERS` maps directories to `@godotengine/*` teams
  (core, network, debugger, gdextension, input, documentation, i18n, audio, rendering…).
* **Commit style** (from `CONTRIBUTING.md`): ≤ 72-char imperative title, optional area
  prefix (`Core:`, `GDScript:`, `Platforms:`), one topic per PR, `git pull --rebase`,
  no fix-up commits inside a PR.
* ⚠️ **AI disclosure policy:** `PULL_REQUEST_TEMPLATE.md` states
  *"Use of AI must be disclosed and should include a description of how it was used."*
  `CONTRIBUTING.md` contains a **commented-out** block demanding a 🤖 in the title plus a
  specific disclosure sentence, and warning that non-disclosing agents will be banned.
  Any contribution sent upstream from this session should follow the disclosure rule.

---

## 10. What's new in the 4.8 cycle (confirmed in this tree *and* upstream notes)

Verified in-code, cross-checked against the official dev-snapshot posts (dev1 Jul 6 →
dev6 Sep 15, 2026):

* **Core:** `GDType` unified member map (1.6× faster property access, −12 MB RAM);
  metadata in text scenes; VCS-friendly Object dumps (one property per line).
* **Rendering:** **ray tracing** in `RenderingDevice` + Vulkan/D3D12; **mip-level texture
  streaming** (`modules/texture_streaming/`, `Texture2D Streamed` import type);
  multi-bounce AO approximation; directional lightmap specular; screen-space contact
  shadows for directional lights; **decals in the Compatibility (GLES3) renderer**;
  build flags to disable RenderingDevice and/or individual renderers (GH-103100).
* **Editor:** main screens converted to **docks** (closable, floatable); docked game view
  by default; 2D/3D/game toolbars redesigned; Find-in-Files replace preview;
  `AndroidSDKManager` automating Android + Java SDK setup.
* **GUI:** `auto_font_size` / `min_font_size` / `max_font_size` on Label & RichTextLabel;
  sticky Tree items; SpinBox `format`; new Control auto-focus algorithm;
  TextEdit/CodeEdit touch support.
* **Scene/3D:** `Trail3D` shipped; `Line3D` declared but unimplemented;
  `BoneSpaceAdjuster3D` + `skin_scale`; `AnimationNodeObservers`.
* **Input:** `Input.get_device_orientation()`, joypad touchpads, gamepad gyro
  auto-calibration, `long_press` on `InputEventScreenTouch`.
* **Platforms:** WinRT/C++ dependency replaced with custom COM+ code (incl. Windows toast
  notifications); Feral GameMode on Linux; visionOS hand tracking & PSVR2 controllers;
  Emscripten 6.0.1; web editor source downloading (the HEAD commit).
* **Scripting:** GDScript syntax-highlighting performance; "disallow strings as comments";
  more crash-resilient language shutdown.
* **Third-party:** SDL 3.4.16, mbedTLS 4.1.0 (PSA Crypto).

---

## 11. Sandbox reality check — what can and cannot be done here

I probed the environment rather than assuming:

| Check | Result |
|---|---|
| `git` history | **Shallow, depth 1** — no blame/diff/log archaeology possible |
| `gh` / network | ✅ reachable (`api.github.com` → HTTP 200); upstream `master` SHA matches HEAD |
| CPU / RAM / disk | **2 cores, 3.8 GiB RAM, 19 GiB free** |
| `scons` | ❌ not installed; `pip install` blocked by **PEP 668** (`externally-managed-environment`) — needs a venv or `--break-system-packages` |
| `clang-format` / `clang-tidy` | ❌ not installed (CI pins v22.1.5 / 22.1.7) |
| `.NET` SDK | ❌ not installed → the `mono` module cannot build |
| `gcc` / `g++` / `python3` | ✅ GCC present, Python 3.11.2 |
| Repo's own Python tooling | ✅ works — `doc_status.py` and `validate_builders.py` both ran successfully |

**Implication:** a full `scons platform=linuxbsd target=editor` build is *not* realistic on
2 cores / 3.8 GiB — Godot's heavy translation units (`rendering_device.cpp`,
`shader_language.cpp`, `text_edit.cpp`, `animation_track_editor.cpp`) each demand well over
1 GiB at `-O2`, and a full editor build is normally a multi-hour, 16 GB+ job. Viable
subsets, if a build is ever wanted, would be something like
`scons target=template_debug dev_build=yes tests=yes -j2 optimize=none module_mono_enabled=no`
with most modules disabled — and even that would likely swap.

---

## 12. Quick navigation map (where to look for what)

| Question | File(s) |
|---|---|
| How does a class get exposed to scripts? | `core/object/class_db.h`, `core/object/gdtype.h`, the `GDCLASS` macro in `core/object/object.h` |
| How is a method called dynamically? | `core/object/method_bind_common.h`, `core/variant/variant_call.cpp` |
| What happens every frame? | `main/main.cpp` → `Main::iteration()` (L4917), `main/main_timer_sync.cpp` |
| How is a scene ticked? | `scene/main/scene_tree.cpp` → `physics_process()` (L640), `scene/main/node.cpp` |
| How does interpolation work? | `scene/main/scene_tree_fti.h|cpp` |
| How is a shader compiled? | `servers/rendering/shader_language.cpp` → `shader_compiler.cpp` → `modules/glslang` → SPIR-V → `drivers/*` |
| How are GPU commands ordered? | `servers/rendering/rendering_device_graph.cpp` |
| How do I add a rendering backend? | `servers/rendering/rendering_device_driver.h` + `rendering_context_driver.h`, see `drivers/metal/README.md` |
| How does a native plugin bind? | `core/extension/gdextension.cpp`, `gdextension_interface.json` |
| How do I keep API back-compat? | add a `*.compat.inc`, and/or an entry in `gdextension_special_compat_hashes.cpp` |
| How is the editor laid out? | `editor/editor_node.cpp`, `editor/docks/editor_dock_manager.cpp`, `editor/editor_main_screen.cpp` |
| How do I add a unit test? | `tests/create_test.py`, then `tests/<area>/test_*.cpp`, doctest macros |
| How do I document a class? | `doc/classes/<Class>.xml` (+ `modules/*/doc_classes/`), validate with `doc/tools/make_rst.py --dry-run` |
| What will CI run on my PR? | `.github/workflows/runner.yml` → `static_checks.yml` → per-platform builds |
