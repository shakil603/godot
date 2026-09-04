/**************************************************************************/
/*  game_master_dock.h                                                    */
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

#include "editor/docks/editor_dock.h"

class Button;
class CheckBox;
class GameMasterAgent;
class Label;
class RichTextLabel;
class TextEdit;
class HBoxContainer;

// The "Game Master" chat panel. It is the ONLY interface the user needs: type what game you want,
// press Send (or Ctrl+Enter), and watch the agent team plan, code, review, generate assets and
// remember the result directly inside the open project.
class GameMasterDock : public EditorDock {
	GDCLASS(GameMasterDock, EditorDock);

	static inline GameMasterDock *singleton = nullptr;

	GameMasterAgent *agent = nullptr;

	Label *status_label = nullptr;
	Label *tokens_label = nullptr;
	Button *settings_button = nullptr;
	Button *clear_button = nullptr;
	Button *send_button = nullptr;
	Button *stop_button = nullptr;
	CheckBox *show_details = nullptr;
	RichTextLabel *chat = nullptr;
	TextEdit *input = nullptr;
	HBoxContainer *setup_banner = nullptr;

	void _on_send();
	void _on_stop();
	void _on_clear();
	void _on_settings();
	void _on_input_gui_input(const Ref<InputEvent> &p_event);
	void _on_log(const String &p_text, const String &p_kind);
	void _on_state_changed(int p_state);
	void _on_role_changed(int p_role);
	void _on_tokens_changed(int p_prompt, int p_completion);
	void _on_run_finished(bool p_success);
	void _on_history_restored();
	void _on_details_toggled(bool p_pressed);
	void _on_meta_clicked(const Variant &p_meta);
	void _update_setup_banner();
	void _append_bubble(const String &p_who, const String &p_text, const Color &p_color);
	void _append_detail(const String &p_text, const Color &p_color);
	void _print_welcome();

protected:
	void _notification(int p_what);

public:
	static GameMasterDock *get_singleton() { return singleton; }

	GameMasterDock();
	~GameMasterDock();
};
