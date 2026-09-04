# Game Master — AI Agent Roadmap

Game Master is this fork's core feature: a **team of AI agents inside the editor** that turns a
chat message into a complete, playable project — no copy-pasting code, no manual importing.
You describe the game; the agents plan, write scenes and scripts directly into `res://`,
generate assets, validate every script with the real GDScript parser, fix mistakes line by
line, remember what they built, and then you press **Play** (or export an APK) like any other
project.

```
 ┌──────────── Game Master dock (chat) ────────────┐
 │  You: "make a 2D platformer with coins and music" │
 └───────────────┬─────────────────────────────────┘
                 ▼
   ┌─────────┐   ┌─────────┐   ┌───────────────────────┐   ┌──────────┐   ┌────────┐
   │ Planner │──▶│  Coder  │──▶│ Artist/Animator/Composer│──▶│ Reviewer │──▶│ Memory │
   └─────────┘   └─────────┘   └───────────────────────┘   └──────────┘   └────────┘
     task list     write_file      request_asset (image /      validate_    save_memory
     under token   patch_file      audio / music / model3d)   script →     (res://.game_master)
     budget        validate_script SpriteFrames / AnimPlayer  patch_file
                   set_main_scene                              line-by-line
                   add_input_action
```

Every box is a *role*: a system prompt + a tool set + a token budget, executed by whichever
LLM you configure. All roles can run on one model, or each on its own (e.g. a cheap model for
Memory, a strong one for Coder).

---

## Where things live

| Piece | Path |
|---|---|
| Chat dock (UI) | `editor/game_master/game_master_dock.cpp/.h` — registered in `EditorNode` next to the History dock, default slot **right-bottom** (tab beside Inspector/Node/History), shortcut **Ctrl+Shift+G**, can float / move / go full-screen like any dock |
| Agent orchestrator + tools | `editor/game_master/game_master_agent.cpp/.h` |
| Settings | **Editor → Editor Settings → Game Master** (`game_master/llm/*`, `game_master/agents/*`, `game_master/limits/*`, `game_master/assets/*`, `game_master/behavior/*`) |
| Per-project memory | `res://.game_master/memory.json`, `res://.game_master/history.json` |

---

## Which APIs you need (give me these and it works)

Only **one** key is required to start. The others unlock real art / sound / 3D — without them
the agents still finish the game with auto-generated placeholder sprites, tones and cube meshes
that you can regenerate later.

### 1. LLM (required) — one of

| Provider setting | Key | Default base URL | Models |
|---|---|---|---|
| **OpenAI compatible** | `OPENAI_API_KEY` | `https://api.openai.com/v1` | `gpt-4o`, `gpt-4.1`, `o4-mini`… |
| ↳ OpenRouter (one key → 300+ models, incl. Claude/Gemini/DeepSeek) | OpenRouter key | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4`, `google/gemini-2.5-pro`, `deepseek/deepseek-chat`… |
| ↳ Groq / DeepSeek / Together / Mistral | their key | `https://api.groq.com/openai/v1` etc. | any tool-calling model |
| ↳ **Local, free**: Ollama / LM Studio | anything (e.g. `local`) | `http://localhost:11434/v1` | `qwen2.5-coder:14b`, `llama3.1`… |
| **Anthropic** | `ANTHROPIC_API_KEY` | `https://api.anthropic.com` | `claude-sonnet-4-20250514`, `claude-opus-4-…` |
| **Google Gemini** | `GEMINI_API_KEY` (AI Studio) | `https://generativelanguage.googleapis.com` | `gemini-2.0-flash`, `gemini-2.5-pro` |

> Recommendation for best code quality: Anthropic Claude Sonnet or OpenAI GPT-4.1 for the
> **Coder/Reviewer**, and a cheap fast model (Gemini Flash / GPT-4o-mini) for **Planner/Memory**.
> Set them per role under *Game Master → Agents*.

### 2. Images / 2D sprites / textures (optional)
*OpenAI Images API compatible* — `game_master/assets/image_api_key`, `image_base_url`, `image_model`.
- OpenAI `gpt-image-1` or `dall-e-3` (key = same OpenAI key)
- Stability AI, Fal.ai, Replicate via any OpenAI-images-compatible proxy

### 3. Sound effects + music (optional)
*ElevenLabs API* — `game_master/assets/audio_api_key` (`xi-api-key`), endpoints
`/v1/sound-generation` (SFX) and `/v1/music`. Alternatives: Suno/Udio via a compatible proxy.

### 4. 3D models (optional)
*Meshy text-to-3D* — `game_master/assets/model3d_api_key`. Alternatives: Tripo3D, Rodin, or Fal.ai
(Hunyuan3D). Meshy's API is asynchronous; the agent starts the task and keeps a placeholder cube
until the `.glb` is dropped in (polling is Phase 3 below).

### 5. Later phases (not needed now)
- **Voice/TTS** for dialog: ElevenLabs TTS or OpenAI TTS (same keys as above).
- **APK export**: no API — needs Android SDK + JDK 17 + this fork's export templates (already part of the engine).

---

## Agent roles (what each one is responsible for)

| Agent | Job | Tools | Guardrails |
|---|---|---|---|
| **Planner** | Splits the request into a numbered file-by-file plan sized for the token budget | `list_files`, `read_file`, `finish(needs_assets)` | Prefers few files; no code |
| **Coder** | Writes `.tscn`/`.gd`/`.tres`, sets main scene, creates input actions, requests assets | `write_file`, `patch_file`, `validate_script`, `set_project_setting`, `set_main_scene`, `add_input_action`, `request_asset`, `open_scene`, `run_project` | **Every `write_file` of a script is parsed immediately** by the engine's GDScript parser; errors are returned with line numbers. Writes containing `TODO`, `...`, "rest of code", markdown fences etc. are **rejected** so no half-finished/unrunnable code lands in the project |
| **Artist / Animator / Composer** | Sprites, textures, 3D meshes, `SpriteFrames`/`AnimationPlayer` resources, music, SFX | `request_asset`, `write_file`, `read_file` | Placeholders are written instantly so scenes never reference missing files; real assets replace them when the API returns |
| **Reviewer** | Gets the parser report for every touched script, fixes **line by line** with `patch_file`, re-validates; also checks node paths / ext_resource paths / input action names across files | same as Coder minus assets | Runs up to 3 passes; refuses to refactor working code |
| **Memory** | Writes the project memory (scenes, scripts, node names, actions, assets, user history) | `save_memory` | Fed to every agent on the next request so follow-ups ("now add a boss") work |

**Token-limit handling**: each role gets `max_output_tokens` per reply and
`max_tool_rounds_per_agent` round trips; the transcript is auto-trimmed (old tool outputs
truncated first) to stay under `max_context_characters`. Billing/quota/401/429 errors are detected
and shown in plain language in the chat instead of silently failing.

---

## Phases

### ✅ Phase 1 — foundation (this commit)
- [x] Game Master chat dock in the editor (send/stop/clear, agent activity log, token counter, setup banner)
- [x] Multi-agent pipeline: Planner → Coder → Artist → Reviewer → Memory
- [x] Three provider backends (OpenAI-compatible, Anthropic, Gemini) with native tool calling
- [x] Per-role model selection, token limits, context trimming
- [x] Direct project tools: write/patch/delete/read/list, real GDScript validation, project settings, main scene, input map, open scene, run
- [x] Forbidden-placeholder filter and tab/space check so unrunnable code is never written
- [x] Asset pipeline with instant placeholders (PNG sprites, WAV tones, OBJ cube) + real generation through Image/Audio/3D APIs
- [x] Persistent project memory and chat history
- [x] Editor Settings page for all keys (stored as password fields in the editor config, never in the project)

### Phase 2 — quality & control
- [ ] Streaming replies (SSE) so text appears while the model is typing
- [ ] "Plan approval" toggle: show the plan and wait for OK before coding
- [ ] Diff preview + one-click undo per run (integrate with EditorUndoRedo / Git)
- [ ] Runtime error feedback loop: capture Output/Debugger errors after `run_project` and hand them to the Reviewer automatically
- [ ] Scene-tree tool (`edit_scene`) that edits open scenes through the SceneTree API instead of raw `.tscn` text
- [ ] Screenshot-to-agent: send a capture of the running game to a vision model for visual QA

### Phase 3 — assets
- [ ] Async polling for Meshy/Tripo 3D jobs → auto-import `.glb`
- [ ] Sprite-sheet slicing + automatic `SpriteFrames` from a single generated sheet
- [ ] Rigged 3D animation via Mixamo-style APIs; 2D skeletal animation
- [ ] TTS dialog and voice-over
- [ ] Asset Library search agent (reuse free CC0 assets before generating)

### Phase 4 — ship
- [ ] One-click **APK / AAB** export from chat ("export for Android") using the built-in Android export
- [ ] Web (HTML5) and desktop export presets generated by the agent
- [ ] Project templates ("2D platformer", "top-down RPG", "3D FPS") as warm starts for the Planner
- [ ] Local-model bundle (Ollama + Qwen-Coder) so Game Master works offline for free

---

## How to use it

1. Build the editor (`scons platform=linuxbsd target=editor` / `platform=windows` / `platform=macos`).
2. Open or create a project. The **Game Master** tab is in the bottom-right dock (Ctrl+Shift+G).
3. Click **Add key…** → paste your LLM key (and optionally image/audio/3D keys) → close.
4. Type: *"Make a 2D endless runner with a jumping dinosaur, cactus obstacles, score UI, jump sound and background music."* → **Build**.
5. Watch the agents work. When it says *Finished*, press ▶ Play. Ask for changes in the same chat — the Memory agent knows the project.
