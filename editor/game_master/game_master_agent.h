/**************************************************************************/
/*  game_master_agent.h                                                   */
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

#pragma once

// Game Master: the multi-agent AI orchestrator that lives inside the editor.
//
// One user request is routed through a pipeline of specialized agents. Each agent is
// a *role* (a system prompt + a tool set + a token budget) that runs on whichever LLM
// backend the user configured in Editor Settings > Game Master. The agents never
// hand code back to the user to paste: every tool call is executed directly against
// the open project (files are written, scenes are created, settings are changed,
// scripts are validated by the real GDScript parser, and the file system is rescanned).
//
//   Planner   -> splits the request into a numbered task list under the token budget.
//   Coder     -> writes scripts/scenes/resources with `write_file` etc.
//   Reviewer  -> runs `validate_script` on every touched script and patches it
//                line-by-line with `patch_file` until the parser reports zero errors.
//   Memory    -> persists a compact project summary in res://.game_master/memory.json
//                so later requests remember what was already built.
//   Artist    -> 2D sprites / textures (image generation API) and 3D models (mesh API).
//   Animator  -> SpriteFrames / AnimationPlayer resources for the generated assets.
//   Composer  -> music and SFX (audio generation API).
//
// The pipeline is fully asynchronous: HTTP calls go through HTTPRequest nodes on the
// main thread, and every step reports progress through the `log` and `state_changed`
// signals that the chat dock listens to.

#include "core/io/http_client.h"
#include "core/object/ref_counted.h"
#include "core/variant/typed_array.h"
#include "scene/main/node.h"

class HTTPRequest;

class GameMasterAgent : public Node {
	GDCLASS(GameMasterAgent, Node);

public:
	enum Role {
		ROLE_PLANNER,
		ROLE_CODER,
		ROLE_REVIEWER,
		ROLE_MEMORY,
		ROLE_ARTIST,
		ROLE_ANIMATOR,
		ROLE_COMPOSER,
		ROLE_MAX,
	};

	enum Provider {
		PROVIDER_OPENAI, // Also any OpenAI-compatible endpoint (OpenRouter, Groq, Ollama, LM Studio...).
		PROVIDER_ANTHROPIC,
		PROVIDER_GEMINI,
		PROVIDER_MAX,
	};

	enum State {
		STATE_IDLE,
		STATE_PLANNING,
		STATE_CODING,
		STATE_REVIEWING,
		STATE_GENERATING_ASSETS,
		STATE_MEMORIZING,
		STATE_ERROR,
	};

	struct Message {
		String role; // "user", "assistant", "tool", "system".
		String content;
		String tool_call_id; // For role == "tool".
		String tool_name; // For role == "tool".
		Array tool_calls; // For role == "assistant" with tool use: [{id, name, arguments(Dictionary)}].
	};

private:
	static inline GameMasterAgent *singleton = nullptr;

	State state = STATE_IDLE;
	Role current_role = ROLE_PLANNER;
	HTTPRequest *http = nullptr;
	HTTPRequest *asset_http = nullptr;
	bool busy = false;
	bool cancel_requested = false;

	// Conversation for the current pipeline run (rebuilt per role from `history`).
	Vector<Message> transcript;
	// Long-lived, user-visible chat history (user/assistant turns only).
	Vector<Message> history;

	// Current run bookkeeping.
	String user_request;
	String plan_text;
	Vector<String> touched_scripts;
	Vector<String> touched_files;
	int step_count = 0;
	int role_round = 0; // How many round trips this role has done so far.
	int consecutive_review_failures = 0;
	int total_prompt_tokens = 0;
	int total_completion_tokens = 0;

	// Asset generation queue: each entry is {type: "image"|"audio"|"model3d", path, prompt, ...}.
	Vector<Dictionary> asset_queue;
	Dictionary current_asset_job;

	// Configuration (read from editor settings each run).
	Provider provider = PROVIDER_OPENAI;
	String api_key;
	String base_url;
	String model_default;
	String model_for_role[ROLE_MAX];
	int max_output_tokens = 4096;
	int max_rounds_per_role = 24;
	int max_context_chars = 120000;
	String image_api_key;
	String image_base_url;
	String image_model;
	String audio_api_key;
	String audio_base_url;
	String model3d_api_key;
	String model3d_base_url;
	bool auto_run_after_build = false;

	void _load_settings();
	void _set_state(State p_state);
	void _log(const String &p_text, const String &p_kind = "info");
	void _fail(const String &p_reason);
	void _finish_run();

	// Role prompts & tools.
	String _system_prompt_for_role(Role p_role) const;
	Array _tools_for_role(Role p_role) const;
	String _project_snapshot() const;
	String _memory_text() const;
	void _save_memory(const String &p_summary);
	String _role_model(Role p_role) const;

	// Pipeline steps.
	void _start_role(Role p_role, const String &p_task);
	void _next_stage();
	void _send_transcript();
	void _trim_transcript();
	void _on_http_completed(int p_result, int p_code, const PackedStringArray &p_headers, const PackedByteArray &p_body);

	// Request builders / parsers per provider.
	Dictionary _build_request_body(const Array &p_tools) const;
	Array _messages_openai() const;
	Array _messages_anthropic(String &r_system) const;
	Array _messages_gemini(String &r_system) const;
	bool _parse_response(const Dictionary &p_json, String &r_text, Array &r_tool_calls, String &r_error);

	// Tool execution (runs on main thread, directly against the project).
	Dictionary _execute_tool(const String &p_name, const Dictionary &p_args);
	Dictionary _tool_list_files(const Dictionary &p_args);
	Dictionary _tool_read_file(const Dictionary &p_args);
	Dictionary _tool_write_file(const Dictionary &p_args);
	Dictionary _tool_patch_file(const Dictionary &p_args);
	Dictionary _tool_delete_file(const Dictionary &p_args);
	Dictionary _tool_validate_script(const Dictionary &p_args);
	Dictionary _tool_set_project_setting(const Dictionary &p_args);
	Dictionary _tool_set_main_scene(const Dictionary &p_args);
	Dictionary _tool_add_input_action(const Dictionary &p_args);
	Dictionary _tool_open_scene(const Dictionary &p_args);
	Dictionary _tool_run_project(const Dictionary &p_args);
	Dictionary _tool_request_asset(const Dictionary &p_args);
	Dictionary _tool_generate_placeholder_image(const Dictionary &p_args);
	Dictionary _tool_generate_tone_audio(const Dictionary &p_args);
	Dictionary _tool_save_memory(const Dictionary &p_args);
	Dictionary _tool_finish(const Dictionary &p_args);

	bool _is_safe_project_path(const String &p_path, String &r_abs) const;
	String _forbidden_token_check(const String &p_code) const;
	void _rescan(const Vector<String> &p_files);

	// Asset pipeline.
	void _process_asset_queue();
	void _on_asset_completed(int p_result, int p_code, const PackedStringArray &p_headers, const PackedByteArray &p_body);
	bool _asset_provider_configured(const String &p_type) const;

protected:
	static void _bind_methods();
	void _notification(int p_what);

public:
	static GameMasterAgent *get_singleton() { return singleton; }

	static String get_role_name(Role p_role);
	static String get_state_name(State p_state);

	bool is_busy() const { return busy; }
	State get_state() const { return state; }
	Role get_current_role() const { return current_role; }
	int get_total_tokens() const { return total_prompt_tokens + total_completion_tokens; }
	bool is_configured() const;
	String get_missing_configuration() const;

	void submit(const String &p_request);
	void cancel();
	void clear_history();
	const Vector<Message> &get_history() const { return history; }

	GameMasterAgent();
	~GameMasterAgent();
};

VARIANT_ENUM_CAST(GameMasterAgent::Role);
VARIANT_ENUM_CAST(GameMasterAgent::Provider);
VARIANT_ENUM_CAST(GameMasterAgent::State);
