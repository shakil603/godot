/**************************************************************************/
/*  game_master_agent.cpp                                                 */
/**************************************************************************/
/*                         This file is part of:                          */
/*                             GODOT ENGINE                               */
/*                        https://godotengine.org                         */
/**************************************************************************/
/* Copyright (c) 2014-present Godot Engine contributors (see AUTHORS.md). */
/* Copyright (c) 2007-2014 Juan Linietsky, Ariel Manzur.                  */
/*                                                                        */
/* Permission is hereby granted, free of charge, to any person obtaining  */
/* a copy of this software and associated documentation files (the        */
/* "Software"), to deal in the Software without restriction, including    */
/* without limitation the rights to use, copy, modify, merge, publish,    */
/* distribute, sublicense, and/or sell copies of the Software, and to     */
/* permit persons to whom the Software is furnished to do so, subject to  */
/* the following conditions:                                              */
/*                                                                        */
/* The above copyright notice and this permission notice shall be         */
/* included in all copies or substantial portions of the Software.        */
/*                                                                        */
/* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,        */
/* EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF     */
/* MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. */
/* IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY   */
/* CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,   */
/* TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE      */
/* SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.                 */
/**************************************************************************/

#include "game_master_agent.h"

#include "core/config/project_settings.h"
#include "core/crypto/crypto_core.h"
#include "core/input/input_event.h"
#include "core/input/input_map.h"
#include "core/io/dir_access.h"
#include "core/io/file_access.h"
#include "core/io/image.h"
#include "core/io/json.h"
#include "core/object/callable_mp.h"
#include "core/object/class_db.h"
#include "core/object/editor_language.h"
#include "core/object/script_language.h"
#include "core/os/keyboard.h"
#include "core/os/time.h"
#include "editor/editor_node.h"
#include "editor/file_system/editor_file_system.h"
#include "editor/run/editor_run_bar.h"
#include "editor/settings/editor_settings.h"
#include "scene/main/http_request.h"

static const char *MEMORY_DIR = "res://.game_master";
static const char *MEMORY_FILE = "res://.game_master/memory.json";
static const char *HISTORY_FILE = "res://.game_master/history.json";

/* -------------------------------------------------------------------------- */
/* Static helpers                                                             */
/* -------------------------------------------------------------------------- */

String GameMasterAgent::get_role_name(Role p_role) {
	switch (p_role) {
		case ROLE_PLANNER:
			return "Planner";
		case ROLE_CODER:
			return "Coder";
		case ROLE_REVIEWER:
			return "Reviewer";
		case ROLE_MEMORY:
			return "Memory";
		case ROLE_ARTIST:
			return "Artist";
		case ROLE_ANIMATOR:
			return "Animator";
		case ROLE_COMPOSER:
			return "Composer";
		default:
			return "Unknown";
	}
}

String GameMasterAgent::get_state_name(State p_state) {
	switch (p_state) {
		case STATE_IDLE:
			return "Idle";
		case STATE_PLANNING:
			return "Planning";
		case STATE_CODING:
			return "Coding";
		case STATE_REVIEWING:
			return "Reviewing";
		case STATE_GENERATING_ASSETS:
			return "Generating assets";
		case STATE_MEMORIZING:
			return "Saving memory";
		case STATE_ERROR:
			return "Error";
	}
	return "Unknown";
}

static Dictionary _schema_param(const String &p_type, const String &p_desc) {
	Dictionary d;
	d["type"] = p_type;
	d["description"] = p_desc;
	return d;
}

static Dictionary _schema_object(const Dictionary &p_props, const Array &p_required) {
	Dictionary d;
	d["type"] = "object";
	d["properties"] = p_props;
	if (!p_required.is_empty()) {
		d["required"] = p_required;
	}
	return d;
}

static Dictionary _tool_def(const String &p_name, const String &p_desc, const Dictionary &p_schema) {
	Dictionary d;
	d["name"] = p_name;
	d["description"] = p_desc;
	d["parameters"] = p_schema;
	return d;
}

static Dictionary _ok(const String &p_msg) {
	Dictionary d;
	d["ok"] = true;
	d["message"] = p_msg;
	return d;
}

static Dictionary _err(const String &p_msg) {
	Dictionary d;
	d["ok"] = false;
	d["error"] = p_msg;
	return d;
}

/* -------------------------------------------------------------------------- */
/* Settings                                                                   */
/* -------------------------------------------------------------------------- */

void GameMasterAgent::_load_settings() {
	provider = (Provider)(int)EDITOR_GET("game_master/llm/provider");
	api_key = String(EDITOR_GET("game_master/llm/api_key")).strip_edges();
	base_url = String(EDITOR_GET("game_master/llm/base_url")).strip_edges();
	model_default = String(EDITOR_GET("game_master/llm/model")).strip_edges();
	max_output_tokens = EDITOR_GET("game_master/limits/max_output_tokens");
	max_rounds_per_role = EDITOR_GET("game_master/limits/max_tool_rounds_per_agent");
	max_context_chars = EDITOR_GET("game_master/limits/max_context_characters");

	model_for_role[ROLE_PLANNER] = String(EDITOR_GET("game_master/agents/planner_model")).strip_edges();
	model_for_role[ROLE_CODER] = String(EDITOR_GET("game_master/agents/coder_model")).strip_edges();
	model_for_role[ROLE_REVIEWER] = String(EDITOR_GET("game_master/agents/reviewer_model")).strip_edges();
	model_for_role[ROLE_MEMORY] = String(EDITOR_GET("game_master/agents/memory_model")).strip_edges();
	model_for_role[ROLE_ARTIST] = String(EDITOR_GET("game_master/agents/artist_model")).strip_edges();
	model_for_role[ROLE_ANIMATOR] = model_for_role[ROLE_ARTIST];
	model_for_role[ROLE_COMPOSER] = model_for_role[ROLE_ARTIST];

	image_api_key = String(EDITOR_GET("game_master/assets/image_api_key")).strip_edges();
	image_base_url = String(EDITOR_GET("game_master/assets/image_base_url")).strip_edges();
	image_model = String(EDITOR_GET("game_master/assets/image_model")).strip_edges();
	audio_api_key = String(EDITOR_GET("game_master/assets/audio_api_key")).strip_edges();
	audio_base_url = String(EDITOR_GET("game_master/assets/audio_base_url")).strip_edges();
	model3d_api_key = String(EDITOR_GET("game_master/assets/model3d_api_key")).strip_edges();
	model3d_base_url = String(EDITOR_GET("game_master/assets/model3d_base_url")).strip_edges();
	auto_run_after_build = EDITOR_GET("game_master/behavior/auto_run_after_build");

	if (base_url.is_empty()) {
		switch (provider) {
			case PROVIDER_OPENAI:
				base_url = "https://api.openai.com/v1";
				break;
			case PROVIDER_ANTHROPIC:
				base_url = "https://api.anthropic.com";
				break;
			case PROVIDER_GEMINI:
				base_url = "https://generativelanguage.googleapis.com";
				break;
			default:
				break;
		}
	}
	if (base_url.ends_with("/")) {
		base_url = base_url.substr(0, base_url.length() - 1);
	}
	if (model_default.is_empty()) {
		switch (provider) {
			case PROVIDER_OPENAI:
				model_default = "gpt-4o";
				break;
			case PROVIDER_ANTHROPIC:
				model_default = "claude-sonnet-4-20250514";
				break;
			case PROVIDER_GEMINI:
				model_default = "gemini-2.0-flash";
				break;
			default:
				break;
		}
	}
}

bool GameMasterAgent::is_configured() const {
	return !String(EDITOR_GET("game_master/llm/api_key")).strip_edges().is_empty();
}

String GameMasterAgent::get_missing_configuration() const {
	if (!is_configured()) {
		return TTR("No LLM API key. Open Editor Settings > Game Master > LLM and paste your key.");
	}
	return String();
}

String GameMasterAgent::_role_model(Role p_role) const {
	if (p_role >= 0 && p_role < ROLE_MAX && !model_for_role[p_role].is_empty()) {
		return model_for_role[p_role];
	}
	return model_default;
}

/* -------------------------------------------------------------------------- */
/* Logging / state                                                            */
/* -------------------------------------------------------------------------- */

void GameMasterAgent::_set_state(State p_state) {
	if (state == p_state) {
		return;
	}
	state = p_state;
	emit_signal(SNAME("state_changed"), (int)state);
}

void GameMasterAgent::_log(const String &p_text, const String &p_kind) {
	emit_signal(SNAME("log"), p_text, p_kind);
}

void GameMasterAgent::_fail(const String &p_reason) {
	_log(p_reason, "error");
	_set_state(STATE_ERROR);
	busy = false;
	Message m;
	m.role = "assistant";
	m.content = vformat(TTR("Game Master stopped: %s"), p_reason);
	history.push_back(m);
	emit_signal(SNAME("run_finished"), false);
	_set_state(STATE_IDLE);
}

void GameMasterAgent::_finish_run() {
	_rescan(touched_files);
	String summary = plan_text.is_empty() ? TTR("Done.") : plan_text;
	Message m;
	m.role = "assistant";
	m.content = summary;
	history.push_back(m);

	// Persist chat history next to the memory file so the next editor session remembers it.
	Array arr;
	for (const Message &msg : history) {
		Dictionary d;
		d["role"] = msg.role;
		d["content"] = msg.content;
		arr.push_back(d);
	}
	DirAccess::make_dir_recursive_absolute(MEMORY_DIR);
	Ref<FileAccess> f = FileAccess::open(HISTORY_FILE, FileAccess::WRITE);
	if (f.is_valid()) {
		f->store_string(JSON::stringify(arr, "\t"));
	}

	busy = false;
	_log(vformat(TTR("Finished. Tokens used this run: %d prompt + %d completion."), total_prompt_tokens, total_completion_tokens), "info");
	_set_state(STATE_IDLE);
	emit_signal(SNAME("run_finished"), true);

	if (auto_run_after_build && EditorRunBar::get_singleton()) {
		EditorRunBar::get_singleton()->play_main_scene();
	}
}

/* -------------------------------------------------------------------------- */
/* Prompts & tools                                                            */
/* -------------------------------------------------------------------------- */

String GameMasterAgent::_project_snapshot() const {
	String out;
	out += "Project name: " + String(GLOBAL_GET("application/config/name")) + "\n";
	out += "Main scene: " + String(GLOBAL_GET("application/run/main_scene")) + "\n";
	out += "Engine: Game Master (Godot 4.x fork). Scripting: GDScript 2.0 (Godot 4 syntax only).\n";
	out += "Files (res://):\n";

	int count = 0;
	List<String> stack;
	stack.push_back("res://");
	while (!stack.is_empty() && count < 400) {
		String dir = stack.front()->get();
		stack.pop_front();
		Ref<DirAccess> da = DirAccess::open(dir);
		if (da.is_null()) {
			continue;
		}
		da->list_dir_begin();
		String n = da->get_next();
		while (!n.is_empty() && count < 400) {
			if (n.begins_with(".")) {
				n = da->get_next();
				continue;
			}
			String full = dir.path_join(n);
			if (da->current_is_dir()) {
				stack.push_back(full);
			} else if (!n.ends_with(".import") && !n.ends_with(".uid")) {
				out += "  " + full + "\n";
				count++;
			}
			n = da->get_next();
		}
		da->list_dir_end();
	}
	if (count == 0) {
		out += "  (empty project)\n";
	}
	return out;
}

String GameMasterAgent::_memory_text() const {
	if (!FileAccess::exists(MEMORY_FILE)) {
		return "(no memory yet: this is the first task in this project)";
	}
	String txt = FileAccess::get_file_as_string(MEMORY_FILE);
	Variant v = JSON::parse_string(txt);
	if (v.get_type() == Variant::DICTIONARY) {
		Dictionary d = v;
		return String(d.get("summary", ""));
	}
	return txt;
}

void GameMasterAgent::_save_memory(const String &p_summary) {
	DirAccess::make_dir_recursive_absolute(MEMORY_DIR);
	Dictionary d;
	d["summary"] = p_summary;
	d["updated"] = Time::get_singleton()->get_datetime_string_from_system();
	Array files;
	for (const String &f : touched_files) {
		files.push_back(f);
	}
	d["last_touched_files"] = files;
	Ref<FileAccess> f = FileAccess::open(MEMORY_FILE, FileAccess::WRITE);
	if (f.is_valid()) {
		f->store_string(JSON::stringify(d, "\t"));
	}
}

String GameMasterAgent::_system_prompt_for_role(Role p_role) const {
	const String common =
			"You are one agent of GAME MASTER, a team of AI agents embedded inside a Godot 4 based game editor. "
			"You do NOT talk to a human who will copy code: every file you produce is written directly into the "
			"open project by calling tools. Never output code in chat; always use tools. "
			"Rules for all code: Godot 4 GDScript only (no Godot 3 syntax, no `yield`, no `onready var` without `@`, "
			"use `@onready`, `@export`, `super()`, typed signals). Never leave placeholders, pseudo-code, ellipses, "
			"TODO/FIXME or 'insert here' comments: every file must be complete and runnable. "
			"Node paths, resource paths and scene structures must be consistent across all files. "
			"Keep answers short: the token budget is limited, so do the work in as few round trips as possible, "
			"and call `finish` as soon as your part is complete.\n\n"
			"PROJECT MEMORY (what earlier tasks built):\n" +
			_memory_text() + "\n\n" + _project_snapshot();

	switch (p_role) {
		case ROLE_PLANNER:
			return common +
					"\nROLE: PLANNER. Turn the user's request into a compact, numbered build plan that a coder can "
					"execute in one pass under a limited token budget. List every scene (.tscn), script (.gd), resource, "
					"input action, project setting and asset (sprite, 3D model, animation, music, sfx) that is required, "
					"with exact res:// paths and the responsibilities of each script. Prefer few files. Do not write code. "
					"You may call `list_files` / `read_file` to inspect the project. When the plan is ready call `finish` "
					"with the full plan in `summary` and set `needs_assets` to true if any image/audio/3D asset must be generated.";
		case ROLE_CODER:
			return common +
					"\nROLE: CODER. Execute the plan exactly, file by file, using `write_file` for every scene and script. "
					"Scenes are written as text `.tscn` (format=3) with `[gd_scene load_steps=N format=3]`, ext_resource entries "
					"for scripts/textures, and nodes with correct `type`/`parent`. Always set the main scene with "
					"`set_main_scene` and create input actions with `add_input_action` instead of assuming they exist. "
					"For textures/sounds/models call `request_asset` (it returns the res:// path you must reference; a placeholder "
					"is produced immediately when no generation API is configured). After writing each .gd file call "
					"`validate_script` and fix every reported line before moving on. Finish by calling `finish` with a short "
					"summary of what was built and how to play it.";
		case ROLE_REVIEWER:
			return common +
					"\nROLE: REVIEWER / FIXER. You receive parser errors for scripts written by the coder. For each error, "
					"`read_file` the script, then repair it precisely with `patch_file` (exact line-based replacement) or rewrite "
					"it with `write_file`, then `validate_script` again. Also check cross-file consistency (node paths used in "
					"`$Path` or `get_node`, signal names, scene ext_resource paths, input action names). Do not refactor working "
					"code. Call `finish` only when every touched script validates with zero errors.";
		case ROLE_MEMORY:
			return common +
					"\nROLE: MEMORY. Write a compact but complete memory of the project for future tasks: purpose of the game, "
					"every scene and script with their role, node names, input actions, assets, known limitations and what the "
					"user asked for over time. Maximum ~1500 words. Call `save_memory` with it, then `finish`.";
		case ROLE_ARTIST:
		case ROLE_ANIMATOR:
		case ROLE_COMPOSER:
			return common +
					"\nROLE: ARTIST / ANIMATOR / COMPOSER. Produce every visual and audio asset the plan needs. For each asset "
					"call `request_asset` with a precise generation prompt (style, size, transparent background for sprites, "
					"loopable for music). For animated sprites, request one image per frame or a sprite sheet and then write a "
					"`SpriteFrames` `.tres` resource (or an `AnimationPlayer` in the scene) that references those images with "
					"`write_file`. Make sure the res:// paths match the ones used in the scenes. Call `finish` with a list of "
					"created assets.";
		default:
			return common;
	}
}

Array GameMasterAgent::_tools_for_role(Role p_role) const {
	Array tools;

	// Shared read tools.
	{
		Dictionary props;
		props["path"] = _schema_param("string", "Directory to list, e.g. res:// or res://scenes");
		Array req;
		req.push_back("path");
		tools.push_back(_tool_def("list_files", "List files and folders in a project directory (recursive).", _schema_object(props, req)));
	}
	{
		Dictionary props;
		props["path"] = _schema_param("string", "res:// path of a text file");
		Array req;
		req.push_back("path");
		tools.push_back(_tool_def("read_file", "Read a text file from the project. Lines are returned prefixed with their 1-based line number.", _schema_object(props, req)));
	}

	if (p_role == ROLE_CODER || p_role == ROLE_REVIEWER || p_role == ROLE_ARTIST || p_role == ROLE_ANIMATOR || p_role == ROLE_COMPOSER) {
		{
			Dictionary props;
			props["path"] = _schema_param("string", "res:// path. Allowed: .gd .tscn .tres .gdshader .json .txt .md .csv .cfg .svg .obj");
			props["content"] = _schema_param("string", "Full file content. Must be complete and runnable.");
			Array req;
			req.push_back("path");
			req.push_back("content");
			tools.push_back(_tool_def("write_file", "Create or overwrite a text file in the project. GDScript files are parsed immediately and errors are returned.", _schema_object(props, req)));
		}
		{
			Dictionary props;
			props["path"] = _schema_param("string", "res:// path of an existing file");
			props["start_line"] = _schema_param("integer", "First line to replace (1-based, inclusive)");
			props["end_line"] = _schema_param("integer", "Last line to replace (1-based, inclusive). Use start_line-1 to insert before start_line.");
			props["new_text"] = _schema_param("string", "Replacement text (may span multiple lines, may be empty to delete)");
			Array req;
			req.push_back("path");
			req.push_back("start_line");
			req.push_back("end_line");
			req.push_back("new_text");
			tools.push_back(_tool_def("patch_file", "Replace an exact line range of a file. Use read_file first to get line numbers. GDScript files are re-validated after patching.", _schema_object(props, req)));
		}
		{
			Dictionary props;
			props["path"] = _schema_param("string", "res:// path of a file to delete");
			Array req;
			req.push_back("path");
			tools.push_back(_tool_def("delete_file", "Delete a file the team created.", _schema_object(props, req)));
		}
		{
			Dictionary props;
			props["path"] = _schema_param("string", "res:// path of a .gd script");
			Array req;
			req.push_back("path");
			tools.push_back(_tool_def("validate_script", "Parse a GDScript file with the engine's real parser and return errors with line numbers.", _schema_object(props, req)));
		}
	}

	if (p_role == ROLE_CODER || p_role == ROLE_REVIEWER) {
		{
			Dictionary props;
			props["name"] = _schema_param("string", "Setting path, e.g. display/window/size/viewport_width");
			props["value"] = _schema_param("string", "Value as JSON (numbers, booleans, strings, arrays)");
			Array req;
			req.push_back("name");
			req.push_back("value");
			tools.push_back(_tool_def("set_project_setting", "Set and save a project setting.", _schema_object(props, req)));
		}
		{
			Dictionary props;
			props["path"] = _schema_param("string", "res:// path of the .tscn to run at start");
			Array req;
			req.push_back("path");
			tools.push_back(_tool_def("set_main_scene", "Set the project's main scene and save project settings.", _schema_object(props, req)));
		}
		{
			Dictionary props;
			props["action"] = _schema_param("string", "Action name, e.g. move_left");
			props["keys"] = _schema_param("string", "Comma separated key names, e.g. 'A,Left' or 'Space'");
			Array req;
			req.push_back("action");
			req.push_back("keys");
			tools.push_back(_tool_def("add_input_action", "Create (or replace) an input action bound to keyboard keys.", _schema_object(props, req)));
		}
		{
			Dictionary props;
			props["path"] = _schema_param("string", "res:// path of the .tscn to open in the editor");
			Array req;
			req.push_back("path");
			tools.push_back(_tool_def("open_scene", "Open a scene in the editor so the user can see it.", _schema_object(props, req)));
		}
		tools.push_back(_tool_def("run_project", "Run the project's main scene (preview) in the editor.", _schema_object(Dictionary(), Array())));
	}

	if (p_role == ROLE_CODER || p_role == ROLE_ARTIST || p_role == ROLE_ANIMATOR || p_role == ROLE_COMPOSER) {
		Dictionary props;
		props["type"] = _schema_param("string", "One of: image, audio, music, model3d");
		props["path"] = _schema_param("string", "Destination res:// path. image -> .png, audio/music -> .wav or .mp3, model3d -> .glb or .obj");
		props["prompt"] = _schema_param("string", "Detailed generation prompt");
		props["width"] = _schema_param("integer", "Image width in pixels (image only, default 64)");
		props["height"] = _schema_param("integer", "Image height in pixels (image only, default 64)");
		props["seconds"] = _schema_param("number", "Duration for audio/music (default 2 for sfx, 30 for music)");
		Array req;
		req.push_back("type");
		req.push_back("path");
		req.push_back("prompt");
		tools.push_back(_tool_def("request_asset", "Generate a game asset with the configured AI asset API (image / audio / music / 3D model). If no API is configured a usable placeholder is created instead. Returns the res:// path to reference.", _schema_object(props, req)));
	}

	if (p_role == ROLE_MEMORY) {
		Dictionary props;
		props["summary"] = _schema_param("string", "The complete project memory text");
		Array req;
		req.push_back("summary");
		tools.push_back(_tool_def("save_memory", "Persist the project memory for future tasks.", _schema_object(props, req)));
	}

	// finish
	{
		Dictionary props;
		props["summary"] = _schema_param("string", "What was done / the plan / the asset list");
		if (p_role == ROLE_PLANNER) {
			props["needs_assets"] = _schema_param("boolean", "true if images, audio or 3D models must be generated");
		}
		Array req;
		req.push_back("summary");
		tools.push_back(_tool_def("finish", "Signal that this agent's job is complete.", _schema_object(props, req)));
	}
	return tools;
}

/* -------------------------------------------------------------------------- */
/* Pipeline                                                                   */
/* -------------------------------------------------------------------------- */

void GameMasterAgent::submit(const String &p_request) {
	if (busy) {
		_log(TTR("Game Master is still working. Press Stop to cancel first."), "error");
		return;
	}
	_load_settings();
	if (!is_configured()) {
		_log(get_missing_configuration(), "error");
		return;
	}

	Message um;
	um.role = "user";
	um.content = p_request;
	history.push_back(um);

	user_request = p_request;
	plan_text = "";
	touched_scripts.clear();
	touched_files.clear();
	asset_queue.clear();
	step_count = 0;
	consecutive_review_failures = 0;
	total_prompt_tokens = 0;
	total_completion_tokens = 0;
	cancel_requested = false;
	busy = true;

	_log(vformat(TTR("Provider: %s | model: %s"), provider == PROVIDER_OPENAI ? "OpenAI-compatible" : (provider == PROVIDER_ANTHROPIC ? "Anthropic" : "Gemini"), model_default), "info");
	_set_state(STATE_PLANNING);
	_start_role(ROLE_PLANNER, "USER REQUEST:\n" + p_request + "\n\nProduce the build plan now.");
}

void GameMasterAgent::cancel() {
	if (!busy) {
		return;
	}
	cancel_requested = true;
	if (http) {
		http->cancel_request();
	}
	if (asset_http) {
		asset_http->cancel_request();
	}
	_fail(TTR("Cancelled by user."));
}

void GameMasterAgent::clear_history() {
	history.clear();
	if (FileAccess::exists(HISTORY_FILE)) {
		Ref<DirAccess> da = DirAccess::open(MEMORY_DIR);
		if (da.is_valid()) {
			da->remove(HISTORY_FILE);
		}
	}
}

void GameMasterAgent::_start_role(Role p_role, const String &p_task) {
	current_role = p_role;
	role_round = 0;
	transcript.clear();
	Message m;
	m.role = "user";
	m.content = p_task;
	transcript.push_back(m);
	_log(vformat("%s (%s) started", get_role_name(p_role), _role_model(p_role)), "role");
	emit_signal(SNAME("role_changed"), (int)p_role);
	_send_transcript();
}

void GameMasterAgent::_trim_transcript() {
	int total = 0;
	for (const Message &m : transcript) {
		total += m.content.length();
	}
	// Keep the task message (index 0) and the last few messages intact; truncate older tool outputs first.
	for (int i = 1; i < transcript.size() - 4 && total > max_context_chars; i++) {
		Message &m = transcript.write[i];
		if (m.role == "tool" && m.content.length() > 200) {
			total -= m.content.length() - 60;
			m.content = "[earlier tool output truncated to save tokens]";
		}
	}
	for (int i = 1; i < transcript.size() - 4 && total > max_context_chars; i++) {
		Message &m = transcript.write[i];
		if (m.role == "assistant" && m.content.length() > 200) {
			total -= m.content.length() - 40;
			m.content = "[earlier reasoning truncated]";
		}
	}
}

Array GameMasterAgent::_messages_openai() const {
	Array out;
	Dictionary sys;
	sys["role"] = "system";
	sys["content"] = _system_prompt_for_role(current_role);
	out.push_back(sys);
	for (const Message &m : transcript) {
		Dictionary d;
		d["role"] = m.role;
		if (m.role == "tool") {
			d["tool_call_id"] = m.tool_call_id;
			d["content"] = m.content;
		} else if (m.role == "assistant") {
			d["content"] = m.content;
			if (!m.tool_calls.is_empty()) {
				Array tcs;
				for (int i = 0; i < m.tool_calls.size(); i++) {
					Dictionary tc = m.tool_calls[i];
					Dictionary o;
					o["id"] = tc["id"];
					o["type"] = "function";
					Dictionary fn;
					fn["name"] = tc["name"];
					fn["arguments"] = JSON::stringify(tc["arguments"]);
					o["function"] = fn;
					tcs.push_back(o);
				}
				d["tool_calls"] = tcs;
			}
		} else {
			d["content"] = m.content;
		}
		out.push_back(d);
	}
	return out;
}

Array GameMasterAgent::_messages_anthropic(String &r_system) const {
	r_system = _system_prompt_for_role(current_role);
	Array out;
	Array pending_tool_results;
	auto flush = [&]() {
		if (!pending_tool_results.is_empty()) {
			Dictionary d;
			d["role"] = "user";
			d["content"] = pending_tool_results;
			out.push_back(d);
			pending_tool_results = Array();
		}
	};
	for (const Message &m : transcript) {
		if (m.role == "tool") {
			Dictionary tr;
			tr["type"] = "tool_result";
			tr["tool_use_id"] = m.tool_call_id;
			tr["content"] = m.content;
			pending_tool_results.push_back(tr);
			continue;
		}
		flush();
		Dictionary d;
		if (m.role == "assistant") {
			d["role"] = "assistant";
			Array content;
			if (!m.content.strip_edges().is_empty()) {
				Dictionary t;
				t["type"] = "text";
				t["text"] = m.content;
				content.push_back(t);
			}
			for (int i = 0; i < m.tool_calls.size(); i++) {
				Dictionary tc = m.tool_calls[i];
				Dictionary u;
				u["type"] = "tool_use";
				u["id"] = tc["id"];
				u["name"] = tc["name"];
				u["input"] = tc["arguments"];
				content.push_back(u);
			}
			if (content.is_empty()) {
				Dictionary t;
				t["type"] = "text";
				t["text"] = "(continuing)";
				content.push_back(t);
			}
			d["content"] = content;
		} else {
			d["role"] = "user";
			d["content"] = m.content;
		}
		out.push_back(d);
	}
	flush();
	return out;
}

Array GameMasterAgent::_messages_gemini(String &r_system) const {
	r_system = _system_prompt_for_role(current_role);
	Array out;
	Array pending_parts;
	auto flush = [&]() {
		if (!pending_parts.is_empty()) {
			Dictionary d;
			d["role"] = "user";
			d["parts"] = pending_parts;
			out.push_back(d);
			pending_parts = Array();
		}
	};
	for (const Message &m : transcript) {
		if (m.role == "tool") {
			Dictionary fr;
			fr["name"] = m.tool_name;
			Dictionary resp;
			resp["result"] = m.content;
			fr["response"] = resp;
			Dictionary part;
			part["functionResponse"] = fr;
			pending_parts.push_back(part);
			continue;
		}
		flush();
		Dictionary d;
		Array parts;
		if (m.role == "assistant") {
			d["role"] = "model";
			if (!m.content.strip_edges().is_empty()) {
				Dictionary t;
				t["text"] = m.content;
				parts.push_back(t);
			}
			for (int i = 0; i < m.tool_calls.size(); i++) {
				Dictionary tc = m.tool_calls[i];
				Dictionary fc;
				fc["name"] = tc["name"];
				fc["args"] = tc["arguments"];
				Dictionary part;
				part["functionCall"] = fc;
				parts.push_back(part);
			}
		} else {
			d["role"] = "user";
			Dictionary t;
			t["text"] = m.content;
			parts.push_back(t);
		}
		d["parts"] = parts;
		out.push_back(d);
	}
	flush();
	return out;
}

Dictionary GameMasterAgent::_build_request_body(const Array &p_tools) const {
	Dictionary body;
	switch (provider) {
		case PROVIDER_OPENAI: {
			body["model"] = _role_model(current_role);
			body["messages"] = _messages_openai();
			body["max_tokens"] = max_output_tokens;
			body["temperature"] = current_role == ROLE_PLANNER ? 0.4 : 0.2;
			Array tools;
			for (int i = 0; i < p_tools.size(); i++) {
				Dictionary t = p_tools[i];
				Dictionary o;
				o["type"] = "function";
				o["function"] = t;
				tools.push_back(o);
			}
			body["tools"] = tools;
			body["tool_choice"] = "auto";
		} break;
		case PROVIDER_ANTHROPIC: {
			String sys;
			body["model"] = _role_model(current_role);
			body["messages"] = _messages_anthropic(sys);
			body["system"] = sys;
			body["max_tokens"] = max_output_tokens;
			Array tools;
			for (int i = 0; i < p_tools.size(); i++) {
				Dictionary t = p_tools[i];
				Dictionary o;
				o["name"] = t["name"];
				o["description"] = t["description"];
				o["input_schema"] = t["parameters"];
				tools.push_back(o);
			}
			body["tools"] = tools;
		} break;
		case PROVIDER_GEMINI: {
			String sys;
			body["contents"] = _messages_gemini(sys);
			Dictionary si;
			Array sparts;
			Dictionary sp;
			sp["text"] = sys;
			sparts.push_back(sp);
			si["parts"] = sparts;
			body["system_instruction"] = si;
			Dictionary gen;
			gen["maxOutputTokens"] = max_output_tokens;
			gen["temperature"] = 0.2;
			body["generationConfig"] = gen;
			Array decls;
			for (int i = 0; i < p_tools.size(); i++) {
				Dictionary t = p_tools[i];
				Dictionary d;
				d["name"] = t["name"];
				d["description"] = t["description"];
				Dictionary params = t["parameters"];
				Dictionary props = params.get("properties", Dictionary());
				if (!props.is_empty()) {
					d["parameters"] = params;
				}
				decls.push_back(d);
			}
			Dictionary tools;
			tools["functionDeclarations"] = decls;
			Array tarr;
			tarr.push_back(tools);
			body["tools"] = tarr;
		} break;
		default:
			break;
	}
	return body;
}

void GameMasterAgent::_send_transcript() {
	if (cancel_requested) {
		return;
	}
	_trim_transcript();
	Dictionary body = _build_request_body(_tools_for_role(current_role));
	String json = JSON::stringify(body);

	Vector<String> headers;
	headers.push_back("Content-Type: application/json");
	String url;
	switch (provider) {
		case PROVIDER_OPENAI:
			url = base_url + "/chat/completions";
			headers.push_back("Authorization: Bearer " + api_key);
			break;
		case PROVIDER_ANTHROPIC:
			url = base_url + "/v1/messages";
			headers.push_back("x-api-key: " + api_key);
			headers.push_back("anthropic-version: 2023-06-01");
			break;
		case PROVIDER_GEMINI:
			url = base_url + "/v1beta/models/" + _role_model(current_role) + ":generateContent";
			headers.push_back("x-goog-api-key: " + api_key);
			break;
		default:
			break;
	}

	Error err = http->request(url, headers, HTTPClient::METHOD_POST, json);
	if (err != OK) {
		_fail(vformat(TTR("Could not start HTTP request (%d). Is another request still running?"), (int)err));
	}
}

bool GameMasterAgent::_parse_response(const Dictionary &p_json, String &r_text, Array &r_tool_calls, String &r_error) {
	if (p_json.has("error")) {
		Variant e = p_json["error"];
		if (e.get_type() == Variant::DICTIONARY) {
			r_error = String(Dictionary(e).get("message", "API error"));
		} else {
			r_error = String(e);
		}
		return false;
	}
	switch (provider) {
		case PROVIDER_OPENAI: {
			Dictionary usage = p_json.get("usage", Dictionary());
			total_prompt_tokens += (int)usage.get("prompt_tokens", 0);
			total_completion_tokens += (int)usage.get("completion_tokens", 0);
			Array choices = p_json.get("choices", Array());
			if (choices.is_empty()) {
				r_error = "Empty response (no choices).";
				return false;
			}
			Dictionary msg = Dictionary(choices[0]).get("message", Dictionary());
			Variant content = msg.get("content", "");
			r_text = content.get_type() == Variant::STRING ? String(content) : String();
			Array tcs = msg.get("tool_calls", Array());
			for (int i = 0; i < tcs.size(); i++) {
				Dictionary tc = tcs[i];
				Dictionary fn = tc.get("function", Dictionary());
				Dictionary o;
				o["id"] = tc.get("id", vformat("call_%d", step_count + i));
				o["name"] = fn.get("name", "");
				Variant args = JSON::parse_string(String(fn.get("arguments", "{}")));
				o["arguments"] = args.get_type() == Variant::DICTIONARY ? args : Variant(Dictionary());
				r_tool_calls.push_back(o);
			}
		} break;
		case PROVIDER_ANTHROPIC: {
			Dictionary usage = p_json.get("usage", Dictionary());
			total_prompt_tokens += (int)usage.get("input_tokens", 0);
			total_completion_tokens += (int)usage.get("output_tokens", 0);
			Array content = p_json.get("content", Array());
			for (int i = 0; i < content.size(); i++) {
				Dictionary block = content[i];
				String type = block.get("type", "");
				if (type == "text") {
					r_text += String(block.get("text", ""));
				} else if (type == "tool_use") {
					Dictionary o;
					o["id"] = block.get("id", vformat("toolu_%d", step_count + i));
					o["name"] = block.get("name", "");
					Variant input = block.get("input", Dictionary());
					o["arguments"] = input.get_type() == Variant::DICTIONARY ? input : Variant(Dictionary());
					r_tool_calls.push_back(o);
				}
			}
		} break;
		case PROVIDER_GEMINI: {
			Dictionary usage = p_json.get("usageMetadata", Dictionary());
			total_prompt_tokens += (int)usage.get("promptTokenCount", 0);
			total_completion_tokens += (int)usage.get("candidatesTokenCount", 0);
			Array cands = p_json.get("candidates", Array());
			if (cands.is_empty()) {
				Dictionary pf = p_json.get("promptFeedback", Dictionary());
				r_error = "Empty response" + (pf.has("blockReason") ? " (blocked: " + String(pf["blockReason"]) + ")" : String(""));
				return false;
			}
			Dictionary content = Dictionary(cands[0]).get("content", Dictionary());
			Array parts = content.get("parts", Array());
			for (int i = 0; i < parts.size(); i++) {
				Dictionary part = parts[i];
				if (part.has("text")) {
					r_text += String(part["text"]);
				}
				if (part.has("functionCall")) {
					Dictionary fc = part["functionCall"];
					Dictionary o;
					o["id"] = vformat("call_%d_%d", step_count, i);
					o["name"] = fc.get("name", "");
					Variant args = fc.get("args", Dictionary());
					o["arguments"] = args.get_type() == Variant::DICTIONARY ? args : Variant(Dictionary());
					r_tool_calls.push_back(o);
				}
			}
		} break;
		default:
			break;
	}
	return true;
}

void GameMasterAgent::_on_http_completed(int p_result, int p_code, const PackedStringArray &p_headers, const PackedByteArray &p_body) {
	if (cancel_requested || !busy) {
		return;
	}
	if (p_result != HTTPRequest::RESULT_SUCCESS) {
		_fail(vformat(TTR("Network error while talking to the LLM (result %d). Check your internet connection, base URL and TLS certificates."), p_result));
		return;
	}
	String body_text = String::utf8((const char *)p_body.ptr(), p_body.size());
	Variant parsed = JSON::parse_string(body_text);
	if (parsed.get_type() != Variant::DICTIONARY) {
		_fail(vformat(TTR("HTTP %d: response is not JSON: %s"), p_code, body_text.substr(0, 400)));
		return;
	}
	Dictionary json = parsed;
	String text;
	Array tool_calls;
	String api_error;
	if (!_parse_response(json, text, tool_calls, api_error) || p_code >= 400) {
		if (api_error.is_empty()) {
			api_error = body_text.substr(0, 400);
		}
		if (p_code == 401 || p_code == 403) {
			api_error = TTR("Authentication failed (check the API key). ") + api_error;
		} else if (p_code == 402 || api_error.to_lower().contains("billing") || api_error.to_lower().contains("quota") || api_error.to_lower().contains("insufficient")) {
			api_error = TTR("Billing / quota problem on your API account. ") + api_error;
		} else if (p_code == 429) {
			api_error = TTR("Rate limited by the provider, wait a bit and try again. ") + api_error;
		}
		_fail(api_error);
		return;
	}

	step_count++;
	Message am;
	am.role = "assistant";
	am.content = text;
	am.tool_calls = tool_calls;
	transcript.push_back(am);
	if (!text.strip_edges().is_empty()) {
		_log(text.strip_edges(), "assistant");
	}
	emit_signal(SNAME("tokens_changed"), total_prompt_tokens, total_completion_tokens);

	if (tool_calls.is_empty()) {
		// The model answered with plain text instead of calling `finish`: treat it as done.
		if (current_role == ROLE_PLANNER) {
			plan_text = text;
		}
		_next_stage();
		return;
	}

	bool finished = false;
	for (int i = 0; i < tool_calls.size(); i++) {
		Dictionary tc = tool_calls[i];
		String name = tc["name"];
		Dictionary args = tc["arguments"];
		Dictionary result;
		if (name == "finish") {
			result = _tool_finish(args);
			finished = true;
		} else {
			result = _execute_tool(name, args);
		}
		Message tm;
		tm.role = "tool";
		tm.tool_call_id = tc["id"];
		tm.tool_name = name;
		tm.content = JSON::stringify(result);
		transcript.push_back(tm);
		if (cancel_requested) {
			return;
		}
	}

	if (finished) {
		_next_stage();
		return;
	}

	role_round++;
	if (role_round >= max_rounds_per_role) {
		_log(vformat(TTR("%s reached the round limit (%d); moving on."), get_role_name(current_role), max_rounds_per_role), "info");
		_next_stage();
		return;
	}
	_send_transcript();
}

void GameMasterAgent::_next_stage() {
	if (cancel_requested) {
		return;
	}
	switch (current_role) {
		case ROLE_PLANNER: {
			if (plan_text.strip_edges().is_empty()) {
				_fail(TTR("Planner produced no plan."));
				return;
			}
			_set_state(STATE_CODING);
			_start_role(ROLE_CODER, "USER REQUEST:\n" + user_request + "\n\nBUILD PLAN (from the planner):\n" + plan_text + "\n\nImplement everything now using the tools.");
		} break;

		case ROLE_CODER: {
			bool needs_assets = current_asset_job.get("needs_assets", false);
			if (needs_assets) {
				_set_state(STATE_GENERATING_ASSETS);
				_start_role(ROLE_ARTIST, "USER REQUEST:\n" + user_request + "\n\nBUILD PLAN:\n" + plan_text + "\n\nThe coder has written the scenes and scripts. Create every asset those files reference (check paths with list_files/read_file), plus animation resources where needed.");
				return;
			}
			_set_state(STATE_REVIEWING);
			current_role = ROLE_ARTIST; // Fall through to the asset/review stage handler.
			_next_stage();
		} break;

		case ROLE_ARTIST:
		case ROLE_ANIMATOR:
		case ROLE_COMPOSER: {
			if (!asset_queue.is_empty()) {
				_set_state(STATE_GENERATING_ASSETS);
				_process_asset_queue();
				return;
			}
			// Validate every touched script with the real parser before deciding whether the reviewer is needed.
			_set_state(STATE_REVIEWING);
			String report;
			int error_count = 0;
			for (const String &s : touched_scripts) {
				Dictionary a;
				a["path"] = s;
				Dictionary r = _tool_validate_script(a);
				if (!(bool)r.get("ok", false)) {
					error_count += (int)r.get("error_count", 1);
					report += "\n" + JSON::stringify(r);
				}
			}
			if (error_count == 0) {
				_log(vformat(TTR("Reviewer: all %d script(s) parse with zero errors."), touched_scripts.size()), "info");
				_set_state(STATE_MEMORIZING);
				_start_role(ROLE_MEMORY, "USER REQUEST:\n" + user_request + "\n\nWHAT WAS BUILT:\n" + plan_text + "\n\nWrite and save the project memory now.");
				return;
			}
			consecutive_review_failures++;
			if (consecutive_review_failures > 3) {
				_log(TTR("Reviewer could not fix every error after 3 passes; finishing anyway. Check the Output panel."), "error");
				_set_state(STATE_MEMORIZING);
				_start_role(ROLE_MEMORY, "USER REQUEST:\n" + user_request + "\n\nWHAT WAS BUILT:\n" + plan_text + "\n\nWrite and save the project memory now.");
				return;
			}
			_start_role(ROLE_REVIEWER, vformat("The following scripts have %d parser error(s). Fix each one line by line, re-validate, then call finish.\n%s", error_count, report));
		} break;

		case ROLE_REVIEWER: {
			// Re-validate; loops back through the ARTIST branch which owns the validation logic.
			current_role = ROLE_ARTIST;
			_next_stage();
		} break;

		case ROLE_MEMORY: {
			if (!FileAccess::exists(MEMORY_FILE)) {
				_save_memory("Request: " + user_request + "\nPlan/result: " + plan_text);
			}
			_finish_run();
		} break;

		default:
			_finish_run();
			break;
	}
}

/* -------------------------------------------------------------------------- */
/* Tools                                                                      */
/* -------------------------------------------------------------------------- */

bool GameMasterAgent::_is_safe_project_path(const String &p_path, String &r_abs) const {
	String p = p_path.strip_edges().replace("\\", "/");
	if (!p.begins_with("res://")) {
		return false;
	}
	if (p.contains("..")) {
		return false;
	}
	String rel = p.trim_prefix("res://");
	if (rel.begins_with(".godot") || rel.begins_with(".import")) {
		return false;
	}
	r_abs = ProjectSettings::get_singleton()->globalize_path(p);
	return true;
}

String GameMasterAgent::_forbidden_token_check(const String &p_code) const {
	// Things that mean "the model did not finish the job". Any of these would make the game fail to run,
	// so the write is rejected and the coder is told exactly which line to fix.
	static const char *forbidden[] = {
		"```", "TODO", "FIXME", "XXX", "<insert", "<your", "your_code_here", "YOUR_CODE", "PLACEHOLDER",
		"# ...", "// ...", "rest of the code", "rest of code", "implement this", "implementation here",
		"code goes here", "omitted for brevity", nullptr
	};
	Vector<String> lines = p_code.split("\n");
	for (int i = 0; i < lines.size(); i++) {
		for (int k = 0; forbidden[k]; k++) {
			if (lines[i].contains(forbidden[k])) {
				return vformat("Line %d contains forbidden placeholder text '%s'. Write the complete real code instead.", i + 1, forbidden[k]);
			}
		}
		if (lines[i].strip_edges() == "...") {
			return vformat("Line %d is an ellipsis placeholder. Write the complete real code instead.", i + 1);
		}
	}
	return String();
}

void GameMasterAgent::_rescan(const Vector<String> &p_files) {
	EditorFileSystem *efs = EditorFileSystem::get_singleton();
	if (!efs) {
		return;
	}
	if (p_files.is_empty()) {
		return;
	}
	efs->update_files(p_files);
	efs->scan_changes();
}

Dictionary GameMasterAgent::_execute_tool(const String &p_name, const Dictionary &p_args) {
	Dictionary result;
	String short_args = JSON::stringify(p_args);
	if (short_args.length() > 160) {
		short_args = short_args.substr(0, 160) + "…";
	}
	_log(vformat("%s → %s %s", get_role_name(current_role), p_name, short_args), "tool");

	if (p_name == "list_files") {
		result = _tool_list_files(p_args);
	} else if (p_name == "read_file") {
		result = _tool_read_file(p_args);
	} else if (p_name == "write_file") {
		result = _tool_write_file(p_args);
	} else if (p_name == "patch_file") {
		result = _tool_patch_file(p_args);
	} else if (p_name == "delete_file") {
		result = _tool_delete_file(p_args);
	} else if (p_name == "validate_script") {
		result = _tool_validate_script(p_args);
	} else if (p_name == "set_project_setting") {
		result = _tool_set_project_setting(p_args);
	} else if (p_name == "set_main_scene") {
		result = _tool_set_main_scene(p_args);
	} else if (p_name == "add_input_action") {
		result = _tool_add_input_action(p_args);
	} else if (p_name == "open_scene") {
		result = _tool_open_scene(p_args);
	} else if (p_name == "run_project") {
		result = _tool_run_project(p_args);
	} else if (p_name == "request_asset") {
		result = _tool_request_asset(p_args);
	} else if (p_name == "save_memory") {
		result = _tool_save_memory(p_args);
	} else {
		result = _err("Unknown tool: " + p_name);
	}

	if (!(bool)result.get("ok", true)) {
		_log(String(result.get("error", "")), "error");
	}
	return result;
}

Dictionary GameMasterAgent::_tool_list_files(const Dictionary &p_args) {
	String path = p_args.get("path", "res://");
	String abs;
	if (!path.begins_with("res://")) {
		path = "res://" + path.trim_prefix("/");
	}
	if (!_is_safe_project_path(path, abs)) {
		return _err("Path must be inside res://");
	}
	Array files;
	List<String> stack;
	stack.push_back(path);
	int count = 0;
	while (!stack.is_empty() && count < 500) {
		String dir = stack.front()->get();
		stack.pop_front();
		Ref<DirAccess> da = DirAccess::open(dir);
		if (da.is_null()) {
			continue;
		}
		da->list_dir_begin();
		String n = da->get_next();
		while (!n.is_empty() && count < 500) {
			if (!n.begins_with(".")) {
				String full = dir.path_join(n);
				if (da->current_is_dir()) {
					stack.push_back(full);
					files.push_back(full + "/");
				} else if (!n.ends_with(".import") && !n.ends_with(".uid")) {
					files.push_back(full);
				}
				count++;
			}
			n = da->get_next();
		}
		da->list_dir_end();
	}
	Dictionary d = _ok(vformat("%d entries", files.size()));
	d["files"] = files;
	return d;
}

Dictionary GameMasterAgent::_tool_read_file(const Dictionary &p_args) {
	String path = p_args.get("path", "");
	String abs;
	if (!_is_safe_project_path(path, abs)) {
		return _err("Invalid path: " + path);
	}
	if (!FileAccess::exists(path)) {
		return _err("File not found: " + path);
	}
	String txt = FileAccess::get_file_as_string(path);
	Vector<String> lines = txt.split("\n");
	String numbered;
	int limit = 0;
	for (int i = 0; i < lines.size(); i++) {
		numbered += vformat("%d| %s\n", i + 1, lines[i]);
		limit += lines[i].length();
		if (limit > 60000) {
			numbered += "[... file truncated at 60000 characters ...]\n";
			break;
		}
	}
	Dictionary d = _ok(vformat("%d lines", lines.size()));
	d["content"] = numbered;
	return d;
}

Dictionary GameMasterAgent::_tool_write_file(const Dictionary &p_args) {
	String path = p_args.get("path", "");
	String content = p_args.get("content", "");
	String abs;
	if (!_is_safe_project_path(path, abs)) {
		return _err("Invalid path (must start with res:// and not touch .godot): " + path);
	}
	if (path.get_file() == "project.godot") {
		return _err("Do not write project.godot directly; use set_project_setting / set_main_scene / add_input_action.");
	}
	static const char *allowed[] = { "gd", "tscn", "tres", "gdshader", "json", "txt", "md", "csv", "cfg", "svg", "obj", "mtl", "gdshaderinc", nullptr };
	String ext = path.get_extension().to_lower();
	bool ext_ok = false;
	for (int i = 0; allowed[i]; i++) {
		if (ext == allowed[i]) {
			ext_ok = true;
			break;
		}
	}
	if (!ext_ok) {
		return _err("Extension ." + ext + " is not allowed for write_file. Binary assets go through request_asset.");
	}
	if (ext == "gd" || ext == "tscn" || ext == "tres" || ext == "gdshader") {
		String bad = _forbidden_token_check(content);
		if (!bad.is_empty()) {
			return _err(bad);
		}
	}
	if (ext == "gd" && content.contains("\t") && content.contains("\n    ")) {
		return _err("Script mixes tabs and spaces for indentation; GDScript rejects that. Use tabs only.");
	}

	Error derr = DirAccess::make_dir_recursive_absolute(path.get_base_dir());
	if (derr != OK && derr != ERR_ALREADY_EXISTS) {
		return _err("Could not create directory " + path.get_base_dir());
	}
	Ref<FileAccess> f = FileAccess::open(path, FileAccess::WRITE);
	if (f.is_null()) {
		return _err("Could not open for writing: " + path);
	}
	f->store_string(content);
	f.unref();

	if (!touched_files.has(path)) {
		touched_files.push_back(path);
	}
	if (EditorFileSystem::get_singleton()) {
		EditorFileSystem::get_singleton()->update_file(path);
	}

	if (ext == "gd") {
		if (!touched_scripts.has(path)) {
			touched_scripts.push_back(path);
		}
		Dictionary v = _tool_validate_script(p_args);
		v["message"] = "Written " + path + ". " + String(v.get("message", ""));
		return v;
	}
	if (ext == "tscn" || ext == "tres") {
		if (!content.begins_with("[gd_scene") && !content.begins_with("[gd_resource")) {
			return _err("Written, but " + path + " does not start with [gd_scene ...] / [gd_resource ...]; it will not load. Rewrite it.");
		}
		// Check that referenced ext_resources exist.
		Vector<String> lines = content.split("\n");
		String missing;
		for (int i = 0; i < lines.size(); i++) {
			const String &l = lines[i];
			if (l.begins_with("[ext_resource")) {
				int pi = l.find("path=\"");
				if (pi >= 0) {
					int pe = l.find("\"", pi + 6);
					String rp = l.substr(pi + 6, pe - pi - 6);
					if (rp.begins_with("res://") && !FileAccess::exists(rp)) {
						missing += vformat("line %d references missing file %s; ", i + 1, rp);
					}
				}
			}
		}
		if (!missing.is_empty()) {
			Dictionary d = _ok("Written " + path + " but with unresolved references: " + missing + "create those files (or request_asset) before finishing.");
			d["warnings"] = missing;
			return d;
		}
	}
	return _ok("Written " + path + " (" + itos(content.length()) + " chars)");
}

Dictionary GameMasterAgent::_tool_patch_file(const Dictionary &p_args) {
	String path = p_args.get("path", "");
	String abs;
	if (!_is_safe_project_path(path, abs)) {
		return _err("Invalid path: " + path);
	}
	if (!FileAccess::exists(path)) {
		return _err("File not found: " + path);
	}
	int start = p_args.get("start_line", 0);
	int end = p_args.get("end_line", 0);
	String new_text = p_args.get("new_text", "");
	String txt = FileAccess::get_file_as_string(path);
	Vector<String> lines = txt.split("\n");
	if (start < 1 || start > lines.size() + 1 || end < start - 1 || end > lines.size()) {
		return _err(vformat("Line range %d-%d is out of bounds (file has %d lines).", start, end, lines.size()));
	}
	Vector<String> out;
	for (int i = 0; i < start - 1; i++) {
		out.push_back(lines[i]);
	}
	if (!new_text.is_empty() || end < start) {
		Vector<String> nl = new_text.split("\n");
		if (new_text.ends_with("\n")) {
			nl.remove_at(nl.size() - 1);
		}
		for (const String &l : nl) {
			out.push_back(l);
		}
	}
	for (int i = end; i < lines.size(); i++) {
		out.push_back(lines[i]);
	}
	String joined = String("\n").join(out);
	Dictionary wa;
	wa["path"] = path;
	wa["content"] = joined;
	Dictionary r = _tool_write_file(wa);
	if ((bool)r.get("ok", false)) {
		r["message"] = vformat("Patched lines %d-%d of %s. ", start, end, path) + String(r.get("message", ""));
	}
	return r;
}

Dictionary GameMasterAgent::_tool_delete_file(const Dictionary &p_args) {
	String path = p_args.get("path", "");
	String abs;
	if (!_is_safe_project_path(path, abs)) {
		return _err("Invalid path: " + path);
	}
	if (path.get_file() == "project.godot") {
		return _err("Refusing to delete project.godot");
	}
	Ref<DirAccess> da = DirAccess::open("res://");
	if (da.is_null() || !da->file_exists(path)) {
		return _err("File not found: " + path);
	}
	da->remove(path);
	if (da->file_exists(path + ".import")) {
		da->remove(path + ".import");
	}
	if (da->file_exists(path + ".uid")) {
		da->remove(path + ".uid");
	}
	touched_scripts.erase(path);
	if (EditorFileSystem::get_singleton()) {
		EditorFileSystem::get_singleton()->update_file(path);
	}
	return _ok("Deleted " + path);
}

Dictionary GameMasterAgent::_tool_validate_script(const Dictionary &p_args) {
	String path = p_args.get("path", "");
	String abs;
	if (!_is_safe_project_path(path, abs)) {
		return _err("Invalid path: " + path);
	}
	if (!FileAccess::exists(path)) {
		return _err("Script not found: " + path);
	}
	String ext = path.get_extension();
	ScriptLanguage *lang = ScriptServer::get_language_for_extension(ext);
	if (!lang) {
		return _err("No script language for extension ." + ext);
	}
	String code = FileAccess::get_file_as_string(path);
	List<EditorLanguage::ScriptError> errors;
	List<EditorLanguage::Warning> warnings;
	bool valid = lang->get_editor_language()->validate(code, path, &errors, &warnings, nullptr, nullptr);

	Vector<String> lines = code.split("\n");
	Array errs;
	for (const EditorLanguage::ScriptError &e : errors) {
		Dictionary d;
		d["line"] = e.start_line;
		d["column"] = e.start_column;
		d["message"] = e.message;
		if (e.start_line >= 1 && e.start_line <= lines.size()) {
			d["source"] = lines[e.start_line - 1];
		}
		errs.push_back(d);
	}
	Dictionary d;
	d["ok"] = valid && errs.is_empty();
	d["path"] = path;
	d["error_count"] = errs.size();
	d["errors"] = errs;
	int warn_count = warnings.size();
	d["warning_count"] = warn_count;
	if (d["ok"]) {
		d["message"] = vformat("%s parses OK (%d warnings).", path, warn_count);
	} else {
		d["error"] = vformat("%s has %d parser error(s). Fix them line by line.", path, errs.size());
	}
	return d;
}

Dictionary GameMasterAgent::_tool_set_project_setting(const Dictionary &p_args) {
	String name = p_args.get("name", "");
	if (name.is_empty() || name.begins_with("_") || name.begins_with("editor/")) {
		return _err("Invalid setting name: " + name);
	}
	Variant value = p_args.get("value", Variant());
	if (value.get_type() == Variant::STRING) {
		String s = value;
		Variant parsed = JSON::parse_string(s);
		if (parsed.get_type() != Variant::NIL) {
			value = parsed;
		}
	}
	ProjectSettings::get_singleton()->set_setting(name, value);
	Error err = ProjectSettings::get_singleton()->save();
	if (err != OK) {
		return _err("Could not save project settings.");
	}
	return _ok("Set " + name + " = " + JSON::stringify(value));
}

Dictionary GameMasterAgent::_tool_set_main_scene(const Dictionary &p_args) {
	String path = p_args.get("path", "");
	String abs;
	if (!_is_safe_project_path(path, abs) || !path.ends_with(".tscn")) {
		return _err("Main scene must be a res://...tscn path.");
	}
	if (!FileAccess::exists(path)) {
		return _err("Scene does not exist yet: " + path + ". Write it first.");
	}
	ProjectSettings::get_singleton()->set_setting("application/run/main_scene", path);
	ProjectSettings::get_singleton()->save();
	return _ok("Main scene set to " + path);
}

Dictionary GameMasterAgent::_tool_add_input_action(const Dictionary &p_args) {
	String action = String(p_args.get("action", "")).strip_edges();
	String keys = p_args.get("keys", "");
	if (action.is_empty() || !action.is_valid_ascii_identifier()) {
		return _err("Action name must be a valid identifier, got: " + action);
	}
	Array events;
	Vector<String> parts = keys.split(",");
	String unknown;
	for (String k : parts) {
		k = k.strip_edges();
		if (k.is_empty()) {
			continue;
		}
		Key code = find_keycode(k);
		if (code == Key::NONE && k.length() == 1) {
			code = find_keycode(k.to_upper());
		}
		if (code == Key::NONE) {
			unknown += k + " ";
			continue;
		}
		Ref<InputEventKey> ev = InputEventKey::create_reference(code, true);
		events.push_back(ev);
	}
	if (events.is_empty()) {
		return _err("No valid key names in '" + keys + "'. Use names like A, D, Left, Right, Space, Enter, Escape, Shift.");
	}
	Dictionary act;
	act["deadzone"] = 0.2;
	act["events"] = events;
	ProjectSettings::get_singleton()->set_setting("input/" + action, act);
	ProjectSettings::get_singleton()->save();
	InputMap::get_singleton()->load_from_project_settings();
	String msg = "Input action '" + action + "' bound to " + keys;
	if (!unknown.is_empty()) {
		msg += " (ignored unknown keys: " + unknown + ")";
	}
	return _ok(msg);
}

Dictionary GameMasterAgent::_tool_open_scene(const Dictionary &p_args) {
	String path = p_args.get("path", "");
	String abs;
	if (!_is_safe_project_path(path, abs) || !FileAccess::exists(path)) {
		return _err("Scene not found: " + path);
	}
	_rescan(touched_files);
	EditorNode::get_singleton()->call_deferred("load_scene", path);
	return _ok("Opening " + path + " in the editor.");
}

Dictionary GameMasterAgent::_tool_run_project(const Dictionary &p_args) {
	String main = GLOBAL_GET("application/run/main_scene");
	if (main.is_empty()) {
		return _err("No main scene set. Call set_main_scene first.");
	}
	_rescan(touched_files);
	if (EditorRunBar::get_singleton()) {
		EditorRunBar::get_singleton()->call_deferred("play_main_scene", false, Vector<String>());
	}
	return _ok("Running " + main);
}

bool GameMasterAgent::_asset_provider_configured(const String &p_type) const {
	if (p_type == "image") {
		return !image_api_key.is_empty();
	}
	if (p_type == "audio" || p_type == "music") {
		return !audio_api_key.is_empty();
	}
	if (p_type == "model3d") {
		return !model3d_api_key.is_empty();
	}
	return false;
}

Dictionary GameMasterAgent::_tool_generate_placeholder_image(const Dictionary &p_args) {
	String path = p_args.get("path", "");
	int w = CLAMP((int)p_args.get("width", 64), 4, 1024);
	int h = CLAMP((int)p_args.get("height", 64), 4, 1024);
	String prompt = String(p_args.get("prompt", "")).to_lower();

	// Deterministic colour from the prompt so different assets are distinguishable.
	uint32_t hash = prompt.hash();
	Color base = Color::from_hsv(float(hash % 360) / 360.0f, 0.65f, 0.9f);
	Color dark = base.darkened(0.45f);

	Ref<Image> img = Image::create_empty(w, h, false, Image::FORMAT_RGBA8);
	bool circle = prompt.contains("ball") || prompt.contains("coin") || prompt.contains("round") || prompt.contains("planet") || prompt.contains("bullet");
	bool transparent = prompt.contains("sprite") || prompt.contains("character") || prompt.contains("player") || prompt.contains("enemy") || prompt.contains("icon") || prompt.contains("transparent") || circle;
	for (int y = 0; y < h; y++) {
		for (int x = 0; x < w; x++) {
			Color c = base;
			float nx = (x + 0.5f) / w - 0.5f;
			float ny = (y + 0.5f) / h - 0.5f;
			if (circle) {
				float r = Math::sqrt(nx * nx + ny * ny);
				if (r > 0.5f) {
					c = Color(0, 0, 0, 0);
				} else if (r > 0.42f) {
					c = dark;
				}
			} else {
				bool border = x < MAX(1, w / 16) || y < MAX(1, h / 16) || x >= w - MAX(1, w / 16) || y >= h - MAX(1, h / 16);
				if (border) {
					c = dark;
				} else if (((x / MAX(1, w / 8)) + (y / MAX(1, h / 8))) % 2 == 0) {
					c = base.lightened(0.12f);
				}
				if (transparent && !border && (Math::abs(nx) > 0.42f || Math::abs(ny) > 0.46f)) {
					c = Color(0, 0, 0, 0);
				}
			}
			img->set_pixel(x, y, c);
		}
	}
	Error derr = DirAccess::make_dir_recursive_absolute(path.get_base_dir());
	if (derr != OK && derr != ERR_ALREADY_EXISTS) {
		return _err("Could not create directory " + path.get_base_dir());
	}
	Error err = img->save_png(path);
	if (err != OK) {
		return _err("Could not save image " + path);
	}
	return _ok("Placeholder image written to " + path + vformat(" (%dx%d). Configure an image API in Editor Settings > Game Master > Assets to get real art.", w, h));
}

Dictionary GameMasterAgent::_tool_generate_tone_audio(const Dictionary &p_args) {
	String path = p_args.get("path", "");
	if (path.get_extension().to_lower() != "wav") {
		path = path.get_basename() + ".wav";
	}
	String type = p_args.get("type", "audio");
	String prompt = String(p_args.get("prompt", "")).to_lower();
	double seconds = p_args.get("seconds", type == "music" ? 8.0 : 0.6);
	seconds = CLAMP(seconds, 0.05, 60.0);
	const int rate = 22050;
	int frames = int(seconds * rate);

	uint32_t hash = prompt.hash();
	double base_freq = 220.0 + double(hash % 440);
	bool noise = prompt.contains("explosion") || prompt.contains("hit") || prompt.contains("crash") || prompt.contains("hurt");
	bool rising = prompt.contains("jump") || prompt.contains("coin") || prompt.contains("pickup") || prompt.contains("power");

	Error derr = DirAccess::make_dir_recursive_absolute(path.get_base_dir());
	if (derr != OK && derr != ERR_ALREADY_EXISTS) {
		return _err("Could not create directory " + path.get_base_dir());
	}
	Ref<FileAccess> f = FileAccess::open(path, FileAccess::WRITE);
	if (f.is_null()) {
		return _err("Could not write " + path);
	}
	const int data_size = frames * 2;
	f->store_buffer((const uint8_t *)"RIFF", 4);
	f->store_32(36 + data_size);
	f->store_buffer((const uint8_t *)"WAVE", 4);
	f->store_buffer((const uint8_t *)"fmt ", 4);
	f->store_32(16);
	f->store_16(1); // PCM
	f->store_16(1); // mono
	f->store_32(rate);
	f->store_32(rate * 2);
	f->store_16(2);
	f->store_16(16);
	f->store_buffer((const uint8_t *)"data", 4);
	f->store_32(data_size);

	uint32_t rng = hash | 1;
	// Simple pentatonic sequence for "music", envelope-shaped tones for sfx.
	static const double scale[] = { 1.0, 9.0 / 8.0, 5.0 / 4.0, 3.0 / 2.0, 5.0 / 3.0, 2.0 };
	double phase = 0.0;
	for (int i = 0; i < frames; i++) {
		double t = double(i) / rate;
		double freq = base_freq;
		double env = 1.0;
		if (type == "music") {
			int note = int(t * 4.0);
			rng = rng * 1664525u + 1013904223u;
			uint32_t pick = (uint32_t(note) * 2654435761u + hash) % 6;
			freq = base_freq * 0.5 * scale[pick];
			double nt = Math::fmod(t, 0.25) / 0.25;
			env = (1.0 - nt) * 0.8 + 0.1;
		} else {
			env = MAX(0.0, 1.0 - t / seconds);
			if (rising) {
				freq = base_freq * (1.0 + t / seconds * 1.5);
			} else {
				freq = base_freq * (1.0 - t / seconds * 0.5);
			}
		}
		phase += 2.0 * Math::PI * freq / rate;
		double s;
		if (noise) {
			rng = rng * 1664525u + 1013904223u;
			s = (double(rng >> 8) / double(1 << 24)) * 2.0 - 1.0;
		} else {
			s = Math::sin(phase) * 0.7 + (Math::sin(phase * 2.0) * 0.2);
		}
		int16_t v = int16_t(CLAMP(s * env * 0.6, -1.0, 1.0) * 32767.0);
		f->store_16((uint16_t)v);
	}
	f.unref();
	Dictionary d = _ok("Placeholder " + type + " written to " + path + ". Configure an audio API in Editor Settings > Game Master > Assets to get real sound.");
	d["path"] = path;
	return d;
}

Dictionary GameMasterAgent::_tool_request_asset(const Dictionary &p_args) {
	String type = String(p_args.get("type", "image")).to_lower();
	String path = p_args.get("path", "");
	String abs;
	if (!_is_safe_project_path(path, abs)) {
		return _err("Invalid asset path: " + path);
	}
	if (type != "image" && type != "audio" && type != "music" && type != "model3d") {
		return _err("type must be image, audio, music or model3d");
	}
	if (!touched_files.has(path)) {
		touched_files.push_back(path);
	}

	if (_asset_provider_configured(type)) {
		Dictionary job = p_args.duplicate();
		job["type"] = type;
		asset_queue.push_back(job);
		// Write a placeholder right now so scenes referencing the path load even before generation completes.
		Dictionary tmp;
		if (type == "image") {
			tmp = _tool_generate_placeholder_image(p_args);
		} else if (type == "model3d") {
			// Placeholder cube .obj; real model will replace it.
			Dictionary a = p_args.duplicate();
			a["path"] = path.get_extension().to_lower() == "obj" ? path : path.get_basename() + ".obj";
			String obj = "o placeholder\nv -0.5 -0.5 -0.5\nv 0.5 -0.5 -0.5\nv 0.5 0.5 -0.5\nv -0.5 0.5 -0.5\nv -0.5 -0.5 0.5\nv 0.5 -0.5 0.5\nv 0.5 0.5 0.5\nv -0.5 0.5 0.5\nf 1 2 3 4\nf 5 8 7 6\nf 1 5 6 2\nf 2 6 7 3\nf 3 7 8 4\nf 5 1 4 8\n";
			a["content"] = obj;
			tmp = _tool_write_file(a);
		} else {
			tmp = _tool_generate_tone_audio(p_args);
		}
		Dictionary d = _ok("Queued " + type + " generation for " + path + " (a placeholder is in place meanwhile).");
		d["path"] = tmp.get("path", path);
		return d;
	}

	// No API for this asset type: build a usable placeholder immediately.
	if (type == "image") {
		Dictionary d = _tool_generate_placeholder_image(p_args);
		d["path"] = path;
		if (EditorFileSystem::get_singleton()) {
			EditorFileSystem::get_singleton()->update_file(path);
		}
		return d;
	}
	if (type == "model3d") {
		Dictionary a = p_args.duplicate();
		String opath = path.get_extension().to_lower() == "obj" ? path : path.get_basename() + ".obj";
		a["path"] = opath;
		a["content"] = "o placeholder\nv -0.5 -0.5 -0.5\nv 0.5 -0.5 -0.5\nv 0.5 0.5 -0.5\nv -0.5 0.5 -0.5\nv -0.5 -0.5 0.5\nv 0.5 -0.5 0.5\nv 0.5 0.5 0.5\nv -0.5 0.5 0.5\nf 1 2 3 4\nf 5 8 7 6\nf 1 5 6 2\nf 2 6 7 3\nf 3 7 8 4\nf 5 1 4 8\n";
		Dictionary d = _tool_write_file(a);
		d["path"] = opath;
		d["message"] = "No 3D model API configured; wrote placeholder cube mesh " + opath + ". Reference THIS path in scenes.";
		return d;
	}
	Dictionary d = _tool_generate_tone_audio(p_args);
	if (EditorFileSystem::get_singleton()) {
		EditorFileSystem::get_singleton()->update_file(String(d.get("path", path)));
	}
	return d;
}

Dictionary GameMasterAgent::_tool_save_memory(const Dictionary &p_args) {
	String summary = p_args.get("summary", "");
	if (summary.strip_edges().is_empty()) {
		return _err("summary is empty");
	}
	_save_memory(summary);
	return _ok("Memory saved (" + itos(summary.length()) + " chars).");
}

Dictionary GameMasterAgent::_tool_finish(const Dictionary &p_args) {
	String summary = p_args.get("summary", "");
	if (current_role == ROLE_PLANNER) {
		plan_text = summary;
		current_asset_job = Dictionary();
		current_asset_job["needs_assets"] = (bool)p_args.get("needs_assets", false);
	} else if (current_role == ROLE_CODER) {
		plan_text = summary.is_empty() ? plan_text : summary;
	}
	_log(vformat("%s finished: %s", get_role_name(current_role), summary.substr(0, 4000)), "assistant");
	return _ok("acknowledged");
}

/* -------------------------------------------------------------------------- */
/* Asset generation (external APIs)                                           */
/* -------------------------------------------------------------------------- */

void GameMasterAgent::_process_asset_queue() {
	if (cancel_requested) {
		return;
	}
	if (asset_queue.is_empty()) {
		current_role = ROLE_ARTIST;
		_next_stage();
		return;
	}
	current_asset_job = asset_queue[0];
	asset_queue.remove_at(0);
	String type = current_asset_job["type"];
	String prompt = current_asset_job["prompt"];
	String path = current_asset_job["path"];
	_log(vformat("Generating %s → %s", type, path), "tool");

	Vector<String> headers;
	headers.push_back("Content-Type: application/json");
	String url;
	Dictionary body;
	if (type == "image") {
		// OpenAI Images API compatible (gpt-image-1 / dall-e-3 / Stability / any compatible proxy).
		String base = image_base_url.is_empty() ? "https://api.openai.com/v1" : image_base_url;
		url = base.trim_suffix("/") + "/images/generations";
		headers.push_back("Authorization: Bearer " + image_api_key);
		body["model"] = image_model.is_empty() ? "gpt-image-1" : image_model;
		body["prompt"] = prompt + ". Game asset, clean edges.";
		// Generate at the API's smallest square size; the result is downscaled to the requested
		// width/height once it arrives (see _on_asset_completed).
		body["size"] = "1024x1024";
		body["n"] = 1;
		if (String(body["model"]).begins_with("dall-e")) {
			body["response_format"] = "b64_json";
		}
	} else if (type == "audio" || type == "music") {
		// ElevenLabs sound generation compatible endpoint (JSON in, audio bytes out).
		String base = audio_base_url.is_empty() ? "https://api.elevenlabs.io/v1" : audio_base_url;
		url = base.trim_suffix("/") + (type == "music" ? "/music" : "/sound-generation");
		headers.push_back("xi-api-key: " + audio_api_key);
		if (type == "music") {
			body["prompt"] = prompt;
			body["music_length_ms"] = int(double(current_asset_job.get("seconds", 30.0)) * 1000.0);
		} else {
			body["text"] = prompt;
			body["duration_seconds"] = double(current_asset_job.get("seconds", 2.0));
		}
	} else {
		// 3D: Meshy-compatible text-to-3D (async task API). We only start the task; result polling is
		// left as a TODO for the user to configure through a proxy that returns a direct GLB URL.
		String base = model3d_base_url.is_empty() ? "https://api.meshy.ai/openapi/v2" : model3d_base_url;
		url = base.trim_suffix("/") + "/text-to-3d";
		headers.push_back("Authorization: Bearer " + model3d_api_key);
		body["mode"] = "preview";
		body["prompt"] = prompt;
		body["art_style"] = "realistic";
	}

	Error err = asset_http->request(url, headers, HTTPClient::METHOD_POST, JSON::stringify(body));
	if (err != OK) {
		_log("Could not start asset request; keeping placeholder for " + path, "error");
		_process_asset_queue();
	}
}

void GameMasterAgent::_on_asset_completed(int p_result, int p_code, const PackedStringArray &p_headers, const PackedByteArray &p_body) {
	if (cancel_requested || !busy) {
		return;
	}
	String type = current_asset_job["type"];
	String path = current_asset_job["path"];
	if (p_result != HTTPRequest::RESULT_SUCCESS || p_code >= 400) {
		String msg = String::utf8((const char *)p_body.ptr(), MIN(p_body.size(), 300));
		_log(vformat("Asset API failed for %s (HTTP %d): %s — placeholder kept.", path, p_code, msg), "error");
		_process_asset_queue();
		return;
	}

	bool is_json = false;
	for (const String &h : p_headers) {
		if (h.to_lower().begins_with("content-type:") && h.to_lower().contains("json")) {
			is_json = true;
		}
	}

	PackedByteArray bytes;
	if (type == "image") {
		Variant v = JSON::parse_string(String::utf8((const char *)p_body.ptr(), p_body.size()));
		if (v.get_type() == Variant::DICTIONARY) {
			Array items = Dictionary(v).get("data", Array());
			if (!items.is_empty()) {
				Dictionary first = items[0];
				String b64 = first.get("b64_json", "");
				if (!b64.is_empty()) {
					CharString cs = b64.ascii();
					bytes.resize(cs.length() / 4 * 3 + 3);
					size_t len = 0;
					if (CryptoCore::b64_decode(bytes.ptrw(), bytes.size(), &len, (const uint8_t *)cs.get_data(), cs.length()) == OK) {
						bytes.resize(len);
					} else {
						bytes.clear();
					}
				} else if (first.has("url")) {
					// Second hop: download the URL.
					current_asset_job["_download"] = true;
					String u = first["url"];
					asset_http->request(u);
					return;
				}
			}
		}
		if (bytes.is_empty()) {
			// Perhaps the response is raw bytes from a proxy.
			if (!is_json) {
				bytes = p_body;
			}
		}
	} else if (type == "audio" || type == "music") {
		if (!is_json) {
			bytes = p_body;
			// ElevenLabs returns mp3.
			if (path.get_extension().to_lower() != "mp3") {
				path = path.get_basename() + ".mp3";
			}
		}
	} else {
		if (!is_json) {
			bytes = p_body;
		} else {
			_log("3D API accepted the task for " + path + " but returned JSON (async task). Placeholder cube kept; download the finished .glb into that path.", "info");
		}
	}

	if (!bytes.is_empty()) {
		Error derr = DirAccess::make_dir_recursive_absolute(path.get_base_dir());
		Ref<FileAccess> f = (derr == OK || derr == ERR_ALREADY_EXISTS) ? FileAccess::open(path, FileAccess::WRITE) : Ref<FileAccess>();
		if (f.is_valid()) {
			f->store_buffer(bytes);
			f.unref();
			_log("Asset saved: " + path, "info");
			if (type == "image") {
				// Downscale to the requested pixel size so sprites keep the intended dimensions.
				int w = current_asset_job.get("width", 0);
				int h = current_asset_job.get("height", 0);
				if (w > 0 && h > 0) {
					Ref<Image> img = Image::load_from_file(path);
					if (img.is_valid() && (img->get_width() != w || img->get_height() != h)) {
						img->resize(w, h, Image::INTERPOLATE_LANCZOS);
						img->save_png(path);
					}
				}
			}
			if (!touched_files.has(path)) {
				touched_files.push_back(path);
			}
			if (EditorFileSystem::get_singleton()) {
				EditorFileSystem::get_singleton()->update_file(path);
			}
		}
	}
	_process_asset_queue();
}

/* -------------------------------------------------------------------------- */
/* Lifecycle                                                                  */
/* -------------------------------------------------------------------------- */

void GameMasterAgent::_notification(int p_what) {
	if (p_what == NOTIFICATION_READY) {
		// Restore previous chat history for this project.
		if (FileAccess::exists(HISTORY_FILE)) {
			Variant v = JSON::parse_string(FileAccess::get_file_as_string(HISTORY_FILE));
			if (v.get_type() == Variant::ARRAY) {
				Array arr = v;
				for (int i = 0; i < arr.size(); i++) {
					Dictionary d = arr[i];
					Message m;
					m.role = d.get("role", "assistant");
					m.content = d.get("content", "");
					history.push_back(m);
				}
				emit_signal(SNAME("history_restored"));
			}
		}
	}
}

void GameMasterAgent::_bind_methods() {
	ClassDB::bind_method(D_METHOD("submit", "request"), &GameMasterAgent::submit);
	ClassDB::bind_method(D_METHOD("cancel"), &GameMasterAgent::cancel);
	ClassDB::bind_method(D_METHOD("is_busy"), &GameMasterAgent::is_busy);

	ADD_SIGNAL(MethodInfo("log", PropertyInfo(Variant::STRING, "text"), PropertyInfo(Variant::STRING, "kind")));
	ADD_SIGNAL(MethodInfo("state_changed", PropertyInfo(Variant::INT, "state")));
	ADD_SIGNAL(MethodInfo("role_changed", PropertyInfo(Variant::INT, "role")));
	ADD_SIGNAL(MethodInfo("tokens_changed", PropertyInfo(Variant::INT, "prompt"), PropertyInfo(Variant::INT, "completion")));
	ADD_SIGNAL(MethodInfo("run_finished", PropertyInfo(Variant::BOOL, "success")));
	ADD_SIGNAL(MethodInfo("history_restored"));

	BIND_ENUM_CONSTANT(ROLE_PLANNER);
	BIND_ENUM_CONSTANT(ROLE_CODER);
	BIND_ENUM_CONSTANT(ROLE_REVIEWER);
	BIND_ENUM_CONSTANT(ROLE_MEMORY);
	BIND_ENUM_CONSTANT(ROLE_ARTIST);
	BIND_ENUM_CONSTANT(ROLE_ANIMATOR);
	BIND_ENUM_CONSTANT(ROLE_COMPOSER);
	BIND_ENUM_CONSTANT(ROLE_MAX);
	BIND_ENUM_CONSTANT(PROVIDER_OPENAI);
	BIND_ENUM_CONSTANT(PROVIDER_ANTHROPIC);
	BIND_ENUM_CONSTANT(PROVIDER_GEMINI);
	BIND_ENUM_CONSTANT(PROVIDER_MAX);
	BIND_ENUM_CONSTANT(STATE_IDLE);
	BIND_ENUM_CONSTANT(STATE_PLANNING);
	BIND_ENUM_CONSTANT(STATE_CODING);
	BIND_ENUM_CONSTANT(STATE_REVIEWING);
	BIND_ENUM_CONSTANT(STATE_GENERATING_ASSETS);
	BIND_ENUM_CONSTANT(STATE_MEMORIZING);
	BIND_ENUM_CONSTANT(STATE_ERROR);
}

GameMasterAgent::GameMasterAgent() {
	singleton = this;
	set_name("GameMasterAgent");

	// Editor settings (Editor > Editor Settings > Game Master).
	EDITOR_DEF("game_master/llm/provider", 0);
	EditorSettings::get_singleton()->add_property_hint(PropertyInfo(Variant::INT, "game_master/llm/provider", PROPERTY_HINT_ENUM, "OpenAI compatible (OpenAI, OpenRouter, Groq, DeepSeek, Ollama...),Anthropic Claude,Google Gemini"));
	EDITOR_DEF("game_master/llm/api_key", "");
	EditorSettings::get_singleton()->add_property_hint(PropertyInfo(Variant::STRING, "game_master/llm/api_key", PROPERTY_HINT_PASSWORD));
	EDITOR_DEF("game_master/llm/base_url", "");
	EditorSettings::get_singleton()->add_property_hint(PropertyInfo(Variant::STRING, "game_master/llm/base_url", PROPERTY_HINT_PLACEHOLDER_TEXT, "Leave empty for the provider default"));
	EDITOR_DEF("game_master/llm/model", "");
	EditorSettings::get_singleton()->add_property_hint(PropertyInfo(Variant::STRING, "game_master/llm/model", PROPERTY_HINT_PLACEHOLDER_TEXT, "gpt-4o / claude-sonnet-4-20250514 / gemini-2.0-flash"));

	EDITOR_DEF("game_master/agents/planner_model", "");
	EDITOR_DEF("game_master/agents/coder_model", "");
	EDITOR_DEF("game_master/agents/reviewer_model", "");
	EDITOR_DEF("game_master/agents/memory_model", "");
	EDITOR_DEF("game_master/agents/artist_model", "");

	EDITOR_DEF("game_master/limits/max_output_tokens", 4096);
	EditorSettings::get_singleton()->add_property_hint(PropertyInfo(Variant::INT, "game_master/limits/max_output_tokens", PROPERTY_HINT_RANGE, "256,32768,1"));
	EDITOR_DEF("game_master/limits/max_tool_rounds_per_agent", 24);
	EditorSettings::get_singleton()->add_property_hint(PropertyInfo(Variant::INT, "game_master/limits/max_tool_rounds_per_agent", PROPERTY_HINT_RANGE, "2,100,1"));
	EDITOR_DEF("game_master/limits/max_context_characters", 120000);
	EditorSettings::get_singleton()->add_property_hint(PropertyInfo(Variant::INT, "game_master/limits/max_context_characters", PROPERTY_HINT_RANGE, "20000,800000,1000"));

	EDITOR_DEF("game_master/assets/image_api_key", "");
	EditorSettings::get_singleton()->add_property_hint(PropertyInfo(Variant::STRING, "game_master/assets/image_api_key", PROPERTY_HINT_PASSWORD));
	EDITOR_DEF("game_master/assets/image_base_url", "");
	EditorSettings::get_singleton()->add_property_hint(PropertyInfo(Variant::STRING, "game_master/assets/image_base_url", PROPERTY_HINT_PLACEHOLDER_TEXT, "https://api.openai.com/v1 (Images API compatible)"));
	EDITOR_DEF("game_master/assets/image_model", "gpt-image-1");
	EDITOR_DEF("game_master/assets/audio_api_key", "");
	EditorSettings::get_singleton()->add_property_hint(PropertyInfo(Variant::STRING, "game_master/assets/audio_api_key", PROPERTY_HINT_PASSWORD));
	EDITOR_DEF("game_master/assets/audio_base_url", "");
	EditorSettings::get_singleton()->add_property_hint(PropertyInfo(Variant::STRING, "game_master/assets/audio_base_url", PROPERTY_HINT_PLACEHOLDER_TEXT, "https://api.elevenlabs.io/v1"));
	EDITOR_DEF("game_master/assets/model3d_api_key", "");
	EditorSettings::get_singleton()->add_property_hint(PropertyInfo(Variant::STRING, "game_master/assets/model3d_api_key", PROPERTY_HINT_PASSWORD));
	EDITOR_DEF("game_master/assets/model3d_base_url", "");
	EditorSettings::get_singleton()->add_property_hint(PropertyInfo(Variant::STRING, "game_master/assets/model3d_base_url", PROPERTY_HINT_PLACEHOLDER_TEXT, "https://api.meshy.ai/openapi/v2"));

	EDITOR_DEF("game_master/behavior/auto_run_after_build", false);

	http = memnew(HTTPRequest);
	http->set_timeout(300);
	http->set_use_threads(true);
	add_child(http);
	http->connect("request_completed", callable_mp(this, &GameMasterAgent::_on_http_completed));

	asset_http = memnew(HTTPRequest);
	asset_http->set_timeout(300);
	asset_http->set_use_threads(true);
	add_child(asset_http);
	asset_http->connect("request_completed", callable_mp(this, &GameMasterAgent::_on_asset_completed));
}

GameMasterAgent::~GameMasterAgent() {
	if (singleton == this) {
		singleton = nullptr;
	}
}
