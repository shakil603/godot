/**************************************************************************/
/*  game_master_dock.cpp                                                  */
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

#include "game_master_dock.h"

#include "core/input/input_event.h"
#include "core/object/callable_mp.h"
#include "editor/editor_node.h"
#include "editor/editor_string_names.h"
#include "editor/game_master/game_master_agent.h"
#include "editor/settings/editor_command_palette.h"
#include "editor/settings/editor_settings.h"
#include "editor/settings/editor_settings_dialog.h"
#include "editor/themes/editor_scale.h"
#include "scene/gui/box_container.h"
#include "scene/gui/button.h"
#include "scene/gui/check_box.h"
#include "scene/gui/label.h"
#include "scene/gui/rich_text_label.h"
#include "scene/gui/text_edit.h"

void GameMasterDock::_append_bubble(const String &p_who, const String &p_text, const Color &p_color) {
	chat->push_color(p_color);
	chat->push_bold();
	chat->add_text(p_who);
	chat->pop();
	chat->pop();
	chat->add_newline();
	chat->add_text(p_text.strip_edges());
	chat->add_newline();
	chat->add_newline();
}

void GameMasterDock::_append_detail(const String &p_text, const Color &p_color) {
	if (!show_details->is_pressed()) {
		return;
	}
	chat->push_color(p_color);
	chat->push_mono();
	chat->add_text("  " + p_text.strip_edges());
	chat->pop();
	chat->pop();
	chat->add_newline();
}

void GameMasterDock::_on_log(const String &p_text, const String &p_kind) {
	const Color font_color = get_theme_color(SNAME("font_color"), EditorStringName(Editor));
	const Color accent = get_theme_color(SNAME("accent_color"), EditorStringName(Editor));
	const Color error_color = get_theme_color(SNAME("error_color"), EditorStringName(Editor));
	const Color dim = Color(font_color, 0.55);

	if (p_kind == "error") {
		chat->push_color(error_color);
		chat->add_text("⚠ " + p_text.strip_edges());
		chat->pop();
		chat->add_newline();
	} else if (p_kind == "assistant") {
		String who = agent ? GameMasterAgent::get_role_name(agent->get_current_role()) : "Game Master";
		_append_bubble(who, p_text, accent);
	} else if (p_kind == "role") {
		chat->push_color(Color(accent, 0.8));
		chat->add_text("▶ " + p_text);
		chat->pop();
		chat->add_newline();
	} else {
		_append_detail(p_text, dim);
	}
}

void GameMasterDock::_on_state_changed(int p_state) {
	GameMasterAgent::State s = (GameMasterAgent::State)p_state;
	status_label->set_text(GameMasterAgent::get_state_name(s));
	bool busy = agent && agent->is_busy();
	send_button->set_disabled(busy);
	stop_button->set_disabled(!busy);
	input->set_editable(!busy);
}

void GameMasterDock::_on_role_changed(int p_role) {
	GameMasterAgent::Role r = (GameMasterAgent::Role)p_role;
	status_label->set_text(GameMasterAgent::get_state_name(agent->get_state()) + " · " + GameMasterAgent::get_role_name(r));
}

void GameMasterDock::_on_tokens_changed(int p_prompt, int p_completion) {
	tokens_label->set_text(vformat("%d tok", p_prompt + p_completion));
}

void GameMasterDock::_on_run_finished(bool p_success) {
	_on_state_changed(GameMasterAgent::STATE_IDLE);
	const Vector<GameMasterAgent::Message> &h = agent->get_history();
	if (!h.is_empty() && h[h.size() - 1].role == "assistant") {
		const Color accent = get_theme_color(SNAME("accent_color"), EditorStringName(Editor));
		_append_bubble("Game Master", h[h.size() - 1].content, p_success ? accent : get_theme_color(SNAME("error_color"), EditorStringName(Editor)));
	}
	input->grab_focus();
}

void GameMasterDock::_on_history_restored() {
	chat->clear();
	_print_welcome();
	const Color font_color = get_theme_color(SNAME("font_color"), EditorStringName(Editor));
	const Color accent = get_theme_color(SNAME("accent_color"), EditorStringName(Editor));
	for (const GameMasterAgent::Message &m : agent->get_history()) {
		_append_bubble(m.role == "user" ? TTR("You") : "Game Master", m.content, m.role == "user" ? font_color : accent);
	}
}

void GameMasterDock::_on_send() {
	if (!agent || agent->is_busy()) {
		return;
	}
	String text = input->get_text().strip_edges();
	if (text.is_empty()) {
		return;
	}
	if (!agent->is_configured()) {
		_update_setup_banner();
		_on_log(agent->get_missing_configuration(), "error");
		return;
	}
	input->set_text("");
	const Color font_color = get_theme_color(SNAME("font_color"), EditorStringName(Editor));
	_append_bubble(TTR("You"), text, font_color);
	agent->submit(text);
	_on_state_changed(agent->get_state());
}

void GameMasterDock::_on_stop() {
	if (agent) {
		agent->cancel();
	}
}

void GameMasterDock::_on_clear() {
	if (agent) {
		agent->clear_history();
	}
	chat->clear();
	_print_welcome();
}

void GameMasterDock::_on_settings() {
	EditorSettingsDialog *dlg = EditorSettingsDialog::get_singleton();
	if (dlg) {
		dlg->popup_edit_settings();
	}
}

void GameMasterDock::_on_details_toggled(bool p_pressed) {
	EditorSettings::get_singleton()->set_project_metadata("game_master", "show_details", p_pressed);
}

void GameMasterDock::_on_meta_clicked(const Variant &p_meta) {
	String m = p_meta;
	if (m == "settings") {
		_on_settings();
	}
}

void GameMasterDock::_on_input_gui_input(const Ref<InputEvent> &p_event) {
	Ref<InputEventKey> k = p_event;
	if (k.is_valid() && k->is_pressed() && !k->is_echo()) {
		if ((k->get_keycode() == Key::ENTER || k->get_keycode() == Key::KP_ENTER) && (k->is_command_or_control_pressed() || !k->is_shift_pressed())) {
			// Enter sends; Shift+Enter inserts a newline.
			_on_send();
			input->accept_event();
		}
	}
}

void GameMasterDock::_update_setup_banner() {
	bool configured = agent && agent->is_configured();
	setup_banner->set_visible(!configured);
}

void GameMasterDock::_print_welcome() {
	const Color font_color = get_theme_color(SNAME("font_color"), EditorStringName(Editor));
	chat->push_color(Color(font_color, 0.7));
	chat->add_text(TTR("Tell Game Master what game you want. A team of AI agents (Planner → Coder → Artist/Animator/Composer → Reviewer → Memory) builds it straight into this project: scenes, scripts, input, assets. Then press Play."));
	chat->pop();
	chat->add_newline();
	chat->add_newline();
}

void GameMasterDock::_notification(int p_what) {
	switch (p_what) {
		case NOTIFICATION_ENTER_TREE:
		case NOTIFICATION_THEME_CHANGED: {
			send_button->set_button_icon(get_editor_theme_icon(SNAME("Play")));
			stop_button->set_button_icon(get_editor_theme_icon(SNAME("Stop")));
			settings_button->set_button_icon(get_editor_theme_icon(SNAME("Tools")));
			clear_button->set_button_icon(get_editor_theme_icon(SNAME("Clear")));
		} break;
		case NOTIFICATION_READY: {
			_update_setup_banner();
			_print_welcome();
			EditorSettings::get_singleton()->connect("settings_changed", callable_mp(this, &GameMasterDock::_update_setup_banner));
		} break;
	}
}

GameMasterDock::GameMasterDock() {
	singleton = this;
	set_name("Game Master");
	set_icon_name("Game");
	set_dock_shortcut(ED_SHORTCUT_AND_COMMAND("docks/open_game_master", TTRC("Open Game Master Dock"), KeyModifierMask::CMD_OR_CTRL | KeyModifierMask::SHIFT | Key::G));
	set_default_slot(EditorDock::DOCK_SLOT_RIGHT_BL);
	set_available_layouts(EditorDock::DOCK_LAYOUT_ALL);

	agent = memnew(GameMasterAgent);
	add_child(agent);
	agent->connect("log", callable_mp(this, &GameMasterDock::_on_log));
	agent->connect("state_changed", callable_mp(this, &GameMasterDock::_on_state_changed));
	agent->connect("role_changed", callable_mp(this, &GameMasterDock::_on_role_changed));
	agent->connect("tokens_changed", callable_mp(this, &GameMasterDock::_on_tokens_changed));
	agent->connect("run_finished", callable_mp(this, &GameMasterDock::_on_run_finished));
	agent->connect("history_restored", callable_mp(this, &GameMasterDock::_on_history_restored));

	VBoxContainer *vb = memnew(VBoxContainer);
	add_child(vb);

	// Header: status + tokens + buttons.
	HBoxContainer *header = memnew(HBoxContainer);
	vb->add_child(header);

	status_label = memnew(Label);
	status_label->set_text(GameMasterAgent::get_state_name(GameMasterAgent::STATE_IDLE));
	status_label->set_h_size_flags(SIZE_EXPAND_FILL);
	status_label->set_clip_text(true);
	header->add_child(status_label);

	tokens_label = memnew(Label);
	tokens_label->set_text("0 tok");
	tokens_label->set_tooltip_text(TTR("Tokens used by the current run (all agents)."));
	header->add_child(tokens_label);

	clear_button = memnew(Button);
	clear_button->set_flat(true);
	clear_button->set_tooltip_text(TTR("Clear chat history"));
	clear_button->connect(SceneStringName(pressed), callable_mp(this, &GameMasterDock::_on_clear));
	header->add_child(clear_button);

	settings_button = memnew(Button);
	settings_button->set_flat(true);
	settings_button->set_tooltip_text(TTR("Open Editor Settings > Game Master (API keys, models, limits)"));
	settings_button->connect(SceneStringName(pressed), callable_mp(this, &GameMasterDock::_on_settings));
	header->add_child(settings_button);

	// Setup banner (shown until an API key exists).
	setup_banner = memnew(HBoxContainer);
	vb->add_child(setup_banner);
	Label *banner_label = memnew(Label);
	banner_label->set_text(TTR("No LLM API key yet."));
	banner_label->set_h_size_flags(SIZE_EXPAND_FILL);
	banner_label->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
	setup_banner->add_child(banner_label);
	Button *banner_btn = memnew(Button);
	banner_btn->set_text(TTR("Add key…"));
	banner_btn->connect(SceneStringName(pressed), callable_mp(this, &GameMasterDock::_on_settings));
	setup_banner->add_child(banner_btn);

	// Chat log.
	chat = memnew(RichTextLabel);
	chat->set_v_size_flags(SIZE_EXPAND_FILL);
	chat->set_selection_enabled(true);
	chat->set_context_menu_enabled(true);
	chat->set_scroll_follow(true);
	chat->set_focus_mode(FOCUS_CLICK);
	chat->connect("meta_clicked", callable_mp(this, &GameMasterDock::_on_meta_clicked));
	vb->add_child(chat);

	// Options row.
	HBoxContainer *opts = memnew(HBoxContainer);
	vb->add_child(opts);
	show_details = memnew(CheckBox);
	show_details->set_text(TTR("Show agent activity"));
	show_details->set_tooltip_text(TTR("Show every tool call (files written, scripts validated, assets generated)."));
	show_details->set_pressed(EditorSettings::get_singleton()->get_project_metadata("game_master", "show_details", true));
	show_details->connect(SceneStringName(toggled), callable_mp(this, &GameMasterDock::_on_details_toggled));
	opts->add_child(show_details);

	// Input row.
	input = memnew(TextEdit);
	input->set_placeholder(TTR("Describe the game or the change you want… (Enter to send, Shift+Enter for a new line)"));
	input->set_custom_minimum_size(Size2(0, 72 * EDSCALE));
	input->set_line_wrapping_mode(TextEdit::LINE_WRAPPING_BOUNDARY);
	input->set_fit_content_height_enabled(false);
	input->connect(SceneStringName(gui_input), callable_mp(this, &GameMasterDock::_on_input_gui_input));
	vb->add_child(input);

	HBoxContainer *actions = memnew(HBoxContainer);
	vb->add_child(actions);
	Control *spacer = memnew(Control);
	spacer->set_h_size_flags(SIZE_EXPAND_FILL);
	actions->add_child(spacer);
	stop_button = memnew(Button);
	stop_button->set_text(TTR("Stop"));
	stop_button->set_disabled(true);
	stop_button->connect(SceneStringName(pressed), callable_mp(this, &GameMasterDock::_on_stop));
	actions->add_child(stop_button);
	send_button = memnew(Button);
	send_button->set_text(TTR("Build"));
	send_button->set_tooltip_text(TTR("Send this request to the Game Master agent team."));
	send_button->connect(SceneStringName(pressed), callable_mp(this, &GameMasterDock::_on_send));
	actions->add_child(send_button);
}

GameMasterDock::~GameMasterDock() {
	if (singleton == this) {
		singleton = nullptr;
	}
}
