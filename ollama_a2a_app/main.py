#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ollama A2A Desktop App
A lightweight Agent-to-Agent communication desktop application.
Refactored for readability and maintainability based on "Readable Code".
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import requests
import threading
import json
import subprocess
import time
import os
import sys
from datetime import datetime
import queue
from pathlib import Path
import re
import google.generativeai as genai
import anthropic
import certifi
import traceback
import logging
from typing import List, Dict, Any, Optional, Tuple, Callable

# --- Constants ---

# For message queue types
MSG_STATUS_OK = "status_ok"
MSG_STATUS_ERROR = "status_error"
MSG_MODELS = "models"
MSG_MODEL_VALIDATION = "model_validation"
MSG_FINISHED = "finished"
MSG_ERROR = "error"
MSG_PROGRESS = "progress"
MSG_SYSTEM = "system"
MSG_AGENT1 = "agent1"
MSG_AGENT2 = "agent2"

# For UI text tags
TAG_AGENT1 = "agent1"
TAG_AGENT2 = "agent2"
TAG_SYSTEM = "system"
TAG_TIMESTAMP = "timestamp"
TAG_ERROR = "error"

# --- Main Application Class ---

class OllamaA2AApp:
    """
    Main application class for the Ollama A2A App.
    Manages the UI, conversation logic, and interactions with AI models.
    """
    
    # --- Model & API Configuration ---
    
    API_PROVIDERS = {
        "Gemini": {
            "models": {
                "Gemini 2.5 Pro (API)": "gemini-2.5-pro",
                "Gemini 2.5 Flash (API)": "gemini-2.5-flash",
            },
            "query_func": "_query_gemini",
            "key_var_name": "gemini_api_key",
            "key_path_name": "gemini_api_key_path",
            "validation_func": "_validate_gemini_key",
        },
        "Claude": {
            "models": {
                "Claude Opus 4 (API)": "claude-opus-4-20250514",
                "Claude Sonnet 4 (API)": "claude-sonnet-4-20250514",
            },
            "query_func": "_query_claude",
            "key_var_name": "claude_api_key",
            "key_path_name": "claude_api_key_path",
            "validation_func": "_validate_claude_key",
        },
        "OpenRouter": {
            "models": {
                "OpenRouter Model 1": "openrouter/model1",
                "OpenRouter Model 2": "openrouter/model2",
            },
            "query_func": "_query_openrouter",
            "key_var_name": "openrouter_api_key",
            "key_path_name": "openrouter_api_key_path",
            "validation_func": "_validate_openrouter_key",
        },
        "Ollama": {
            "query_func": "_query_ollama",
        }
    }
    
    # --- Initialization ---

    def __init__(self, root: tk.Tk):
        self.root = root
        self.message_queue = queue.Queue()
        
        self._setup_ssl()
        self._setup_variables()
        self._setup_window()
        self._setup_ui()
        
        self._load_api_keys()
        self.check_ollama_status()
        self.check_queue()

    def _setup_ssl(self):
        """Sets the SSL certificate path."""
        os.environ["SSL_CERT_FILE"] = certifi.where()

    def _setup_variables(self):
        """Initializes application variables."""
        self.ollama_url = "http://localhost:11434"
        self.available_models: List[str] = []
        self.is_running = False
        self.current_thread: Optional[threading.Thread] = None
        
        # --- Configurable Tkinter Variables ---
        self.agent1_model = tk.StringVar()
        self.agent2_model = tk.StringVar()
        self.max_rounds = tk.IntVar(value=3)
        self.auto_mode = tk.BooleanVar(value=False)
        self.timeout_setting = tk.IntVar(value=600)
        self.gemini_api_key = tk.StringVar()
        self.claude_api_key = tk.StringVar()
        self.openrouter_api_key = tk.StringVar()
        self.openrouter_model_1_name = tk.StringVar()
        self.openrouter_model_2_name = tk.StringVar()

        # --- UI Component References ---
        self.agent1_combo: Optional[ttk.Combobox] = None
        self.agent2_combo: Optional[ttk.Combobox] = None
        
        # --- Paths and Sound ---
        self.sound_played = False
        project_root = Path(__file__).parent.parent
        self.bell_sound_path = project_root / "bell.mp3"
        self.gemini_api_key_path = project_root / ".gemini_api_key"
        self.claude_api_key_path = project_root / ".claude_api_key"
        self.openrouter_api_key_path = project_root / ".openrouter_api_key"
        self.openrouter_model_1_name_path = project_root / ".openrouter_model_1_name"
        self.openrouter_model_2_name_path = project_root / ".openrouter_model_2_name"

        # Configure logging
        log_file_path = project_root / "ollama_a2a_app.log"
        logging.basicConfig(
            level=logging.ERROR,
            format='%(asctime)s - %(levelname)s - %(message)s',
            filename=log_file_path,
            filemode='a'
        )

    def _load_api_keys(self):
        """Loads API keys from their respective files on startup."""
        self._load_single_api_key(self.gemini_api_key_path, self.gemini_api_key, "Gemini")
        self._load_single_api_key(self.claude_api_key_path, self.claude_api_key, "Claude")
        self._load_single_api_key(self.openrouter_api_key_path, self.openrouter_api_key, "OpenRouter")
        self._load_single_api_key(self.openrouter_model_1_name_path, self.openrouter_model_1_name, "OpenRouter Model 1")
        self._load_single_api_key(self.openrouter_model_2_name_path, self.openrouter_model_2_name, "OpenRouter Model 2")

    def _load_single_api_key(self, path: Path, var: tk.StringVar, name: str):
        """Helper to load one API key."""
        if not path.exists():
            return
        try:
            key = path.read_text().strip()
            if key:
                var.set(key)
                self.message_queue.put((MSG_STATUS_OK, f"✅ {name} APIキー自動読み込み済み"))
        except Exception as e:
            logging.error(f"{name} APIキーファイルの読み込みエラー: {e}")

    # --- UI Setup ---

    def _setup_window(self):
        """Configures the main application window."""
        self.root.title("Ollama A2A - Agent to Agent Communication")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)
        
        if sys.platform == "darwin":
            style = ttk.Style()
            style.theme_use("aqua")

    def _setup_ui(self):
        """Builds the main user interface."""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(3, weight=1)

        title_label = ttk.Label(main_frame, text="🤖 Ollama A2A Communication", font=("SF Pro Display", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        self._create_settings_panel(main_frame)
        self._create_input_panel(main_frame)
        self._create_conversation_panel(main_frame)
        self._create_control_panel(main_frame)
        self._create_status_bar(main_frame)

    def _create_settings_panel(self, parent: ttk.Frame):
        """Creates the agent and conversation settings panel."""
        frame = ttk.LabelFrame(parent, text="⚙️ エージェント設定", padding="10")
        frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

        ttk.Label(frame, text="Agent 1 (分析役):").grid(row=0, column=0, padx=(0, 10))
        self.agent1_combo = ttk.Combobox(frame, textvariable=self.agent1_model)
        self.agent1_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 20))

        ttk.Label(frame, text="Agent 2 (評価役):").grid(row=0, column=2, padx=(0, 10))
        self.agent2_combo = ttk.Combobox(frame, textvariable=self.agent2_model)
        self.agent2_combo.grid(row=0, column=3, sticky=(tk.W, tk.E))

        ttk.Label(frame, text="対話ラウンド数:").grid(row=1, column=0, pady=(10, 0))
        ttk.Spinbox(frame, from_=1, to=10, textvariable=self.max_rounds, width=10).grid(row=1, column=1, sticky=tk.W, padx=(0, 20), pady=(10, 0))

        ttk.Label(frame, text="タイムアウト(秒):").grid(row=1, column=2, pady=(10, 0))
        ttk.Spinbox(frame, from_=60, to=600, textvariable=self.timeout_setting, width=10).grid(row=1, column=3, sticky=tk.W, pady=(10, 0))

        ttk.Checkbutton(frame, text="自動連続実行", variable=self.auto_mode).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))
        ttk.Button(frame, text="⚙️ 設定", command=self.open_settings_dialog).grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(10, 0))

    def _create_input_panel(self, parent: ttk.Frame):
        """Creates the initial prompt input panel with placeholder behavior."""
        frame = ttk.LabelFrame(parent, text="💭 プロンプト", padding="10")
        frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        text_container = ttk.Frame(frame)
        text_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        text_container.columnconfigure(0, weight=1)
        text_container.rowconfigure(0, weight=1)

        self.input_text = tk.Text(text_container, height=8, wrap=tk.WORD)
        self.input_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        scrollbar = ttk.Scrollbar(text_container, orient="vertical", command=self.input_text.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.input_text.configure(yscrollcommand=scrollbar.set)

        # Placeholder setup
        self.placeholder_text = "AIの未来について議論してください。技術的な可能性と社会的な影響の両面から考察してください。"
        self.placeholder_color = '#999999'
        self.default_fg_color = self.input_text.cget('foreground')

        def on_focus_in(event):
            if self.input_text.get("1.0", "end-1c") == self.placeholder_text:
                self.input_text.delete("1.0", tk.END)
                self.input_text.config(foreground=self.default_fg_color)

        def on_focus_out(event):
            if not self.input_text.get("1.0", "end-1c"):
                self.input_text.insert("1.0", self.placeholder_text)
                self.input_text.config(foreground=self.placeholder_color)

        self.input_text.insert("1.0", self.placeholder_text)
        self.input_text.config(foreground=self.placeholder_color)

        self.input_text.bind('<FocusIn>', on_focus_in)
        self.input_text.bind('<FocusOut>', on_focus_out)
        self.input_text.bind('<Shift-Return>', self.on_shift_enter)
        self.input_text.bind('<Control-Return>', self.on_shift_enter)

        hint_label = ttk.Label(frame, text="💡 Shift+Enter で対話開始", font=("SF Pro Display", 9), foreground="#666666")
        hint_label.grid(row=1, column=0, sticky=tk.E, pady=(5, 0))

    def _create_conversation_panel(self, parent: ttk.Frame):
        """Creates the conversation display panel."""
        frame = ttk.LabelFrame(parent, text="💬 エージェント間対話", padding="10")
        frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.conversation_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, font=("Monaco", 11))
        self.conversation_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.conversation_text.tag_config(TAG_AGENT1, foreground="#0066CC", font=("Monaco", 11, "bold"))
        self.conversation_text.tag_config(TAG_AGENT2, foreground="#CC6600", font=("Monaco", 11, "bold"))
        self.conversation_text.tag_config(TAG_SYSTEM, foreground="#666666", font=("Monaco", 10, "italic"))
        self.conversation_text.tag_config(TAG_TIMESTAMP, foreground="#999999", font=("Monaco", 9))
        self.conversation_text.tag_config(TAG_ERROR, foreground="#CC0000", font=("Monaco", 10, "bold"))

    def _create_control_panel(self, parent: ttk.Frame):
        """Creates the main control buttons panel."""
        frame = ttk.Frame(parent)
        frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        self.start_button = ttk.Button(frame, text="🚀 対話開始", command=self.start_conversation, style="Accent.TButton")
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_button = ttk.Button(frame, text="⏹ 停止", command=self.stop_conversation, state="disabled")
        self.stop_button.pack(side=tk.LEFT, padx=(0, 10))

        self.clear_button = ttk.Button(frame, text="🗑 クリア", command=self.clear_conversation)
        self.clear_button.pack(side=tk.LEFT, padx=(0, 10))

        self.save_button = ttk.Button(frame, text="💾 保存(.md)", command=self.save_conversation)
        self.save_button.pack(side=tk.LEFT, padx=(0, 10))

    def _create_status_bar(self, parent: ttk.Frame):
        """Creates the status bar at the bottom."""
        frame = ttk.Frame(parent)
        frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E))
        frame.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(frame, text="準備完了 - Ollamaサービスを確認してください")
        self.status_label.grid(row=0, column=0, sticky=tk.W)

        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.grid(row=0, column=1, sticky=tk.E, padx=(10, 0))

    # --- Settings Dialog ---

    def open_settings_dialog(self):
        """Opens the API key and settings dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.title("設定")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.focus_set()
        dialog.resizable(False, False)

        dialog_frame = ttk.Frame(dialog, padding="20")
        dialog_frame.pack(fill=tk.BOTH, expand=True)

        # API Key Section
        api_frame = ttk.LabelFrame(dialog_frame, text="🔑 API設定", padding="10")
        api_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self._create_api_key_entry(api_frame, "Gemini", self.gemini_api_key, 0)
        self._create_api_key_entry(api_frame, "Claude", self.claude_api_key, 1)
        self._create_openrouter_settings_entry(api_frame, 2)

        # Test Section
        test_frame = ttk.LabelFrame(dialog_frame, text="🛠️ テストと確認", padding="10")
        test_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(10, 0))
        test_frame.columnconfigure(0, weight=1)
        test_frame.columnconfigure(1, weight=1)
        
        ttk.Button(test_frame, text="🔍 Ollama確認", command=self.check_ollama_status_sync_and_show_popup).grid(row=0, column=0, padx=(0, 5), pady=5, sticky="ew")
        ttk.Button(test_frame, text="🔊 音声テスト", command=self.test_audio_system).grid(row=0, column=1, padx=(5, 0), pady=5, sticky="ew")

        # Close Button
        ttk.Button(dialog_frame, text="閉じる", command=dialog.destroy).grid(row=2, column=0, pady=(20, 0))

        dialog.wait_window(dialog)

    def _create_api_key_entry(self, parent: ttk.Frame, service_name: str, key_var: tk.StringVar, row: int):
        """Helper to create a single API key entry in the settings dialog."""
        frame = ttk.LabelFrame(parent, text=f"{service_name} API設定", padding="10")
        frame.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=5)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="API Key:").grid(row=0, column=0, padx=(0, 10), sticky=tk.W)
        entry = ttk.Entry(frame, textvariable=key_var, show="*", width=40)
        entry.grid(row=0, column=1, sticky="ew")
        
        save_command = lambda: self._save_api_key_handler(service_name, entry.get(), parent)
        ttk.Button(frame, text="保存 & 検証", command=save_command).grid(row=1, column=0, columnspan=2, pady=(10, 0))

    def _create_openrouter_settings_entry(self, parent: ttk.Frame, row: int):
        """Helper to create the OpenRouter settings entry in the settings dialog."""
        frame = ttk.LabelFrame(parent, text="OpenRouter API設定", padding="10")
        frame.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=5)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="API Key:").grid(row=0, column=0, padx=(0, 10), sticky=tk.W)
        key_entry = ttk.Entry(frame, textvariable=self.openrouter_api_key, show="*", width=40)
        key_entry.grid(row=0, column=1, sticky="ew")

        ttk.Label(frame, text="Model 1 Name:").grid(row=1, column=0, padx=(0, 10), sticky=tk.W)
        model_1_entry = ttk.Entry(frame, textvariable=self.openrouter_model_1_name, width=40)
        model_1_entry.grid(row=1, column=1, sticky="ew")

        ttk.Label(frame, text="Model 2 Name:").grid(row=2, column=0, padx=(0, 10), sticky=tk.W)
        model_2_entry = ttk.Entry(frame, textvariable=self.openrouter_model_2_name, width=40)
        model_2_entry.grid(row=2, column=1, sticky="ew")
        
        save_command = lambda: self._save_openrouter_settings(key_entry.get(), model_1_entry.get(), model_2_entry.get(), parent)
        ttk.Button(frame, text="保存 & 検証", command=save_command).grid(row=3, column=0, columnspan=2, pady=(10, 0))

    # --- API Key Handling ---

    def _save_api_key_handler(self, service_name: str, key: str, dialog: tk.Widget):
        """Handles the save button click for an API key."""
        if service_name == "OpenRouter":
            # This is handled by _save_openrouter_settings
            return

        provider_info = self.API_PROVIDERS.get(service_name)
        if not provider_info:
            return

        key_path = getattr(self, provider_info["key_path_name"])
        key_var = getattr(self, provider_info["key_var_name"])
        validation_func_name = provider_info["validation_func"]
        validation_func = getattr(self, validation_func_name)

        self._save_api_key(key, key_path, key_var, service_name, validation_func, dialog)

    def _save_openrouter_settings(self, key: str, model_1_name: str, model_2_name: str, dialog: tk.Widget):
        """Saves and validates OpenRouter settings."""
        if not key:
            messagebox.showwarning("警告", "OpenRouter APIキーが入力されていません", parent=dialog)
            return
        if not model_1_name or not model_2_name:
            messagebox.showwarning("警告", "OpenRouterのモデル名が入力されていません", parent=dialog)
            return

        try:
            self._validate_openrouter_key(key, [model_1_name, model_2_name])
            self.openrouter_api_key_path.write_text(key)
            self.openrouter_model_1_name_path.write_text(model_1_name)
            self.openrouter_model_2_name_path.write_text(model_2_name)
            self.openrouter_api_key.set(key)
            self.openrouter_model_1_name.set(model_1_name)
            self.openrouter_model_2_name.set(model_2_name)
            messagebox.showinfo("成功", "OpenRouterの設定が正常に保存されました", parent=dialog)
            self.message_queue.put((MSG_STATUS_OK, "✅ OpenRouter APIキー設定済み"))
        except Exception as e:
            messagebox.showerror("エラー", f"OpenRouterの検証に失敗しました: {e}", parent=dialog)
            logging.error(f"OpenRouterの検証に失敗しました: {e}")

    def _save_api_key(self, key: str, key_path: Path, key_var: tk.StringVar, service_name: str, validation_func: Callable[[str], None], dialog: tk.Widget):
        """Generic logic to validate and save an API key."""
        if not key:
            messagebox.showwarning("警告", f"{service_name} APIキーが入力されていません", parent=dialog)
            return

        try:
            validation_func(key)
            key_path.write_text(key)
            key_var.set(key)
            messagebox.showinfo("成功", f"{service_name} APIキーが正常に保存されました", parent=dialog)
            self.message_queue.put((MSG_STATUS_OK, f"✅ {service_name} APIキー設定済み"))
        except Exception as e:
            messagebox.showerror("エラー", f"{service_name} APIキーの検証に失敗しました: {e}", parent=dialog)
            logging.error(f"{service_name} APIキーの検証に失敗しました: {e}")

    def _validate_gemini_key(self, api_key: str):
        """Validation logic for Gemini API key."""
        genai.configure(api_key=api_key)
        genai.get_model('models/gemini-2.5-pro')

    def _validate_claude_key(self, api_key: str):
        """Validation logic for Claude API key."""
        client = anthropic.Anthropic(api_key=api_key, timeout=60.0)
        client.models.list()

    def _validate_openrouter_key(self, api_key: str, model_names: List[str]):
        """Validation logic for OpenRouter API key and models."""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        response = requests.get(f"https://openrouter.ai/api/v1/models", headers=headers)
        response.raise_for_status()
        models = response.json().get("data", [])
        available_models = {model["id"] for model in models}
        for model_name in model_names:
            if model_name not in available_models:
                raise ValueError(f"モデル '{model_name}' はOpenRouterで利用できません。")

    # --- Conversation Logic ---

    def on_shift_enter(self, event: tk.Event):
        """Shift+Enter key event handler to start conversation."""
        self.start_conversation()
        return "break"

    def start_conversation(self):
        """Starts the agent-to-agent conversation."""
        if not self._validate_preconditions():
            return

        self.is_running = True
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.progress.start()
        self.sound_played = False

        initial_prompt = self.input_text.get("1.0", tk.END).strip()
        if initial_prompt == self.placeholder_text:
            initial_prompt = ""
        agent1_model = self.agent1_model.get()
        agent2_model = self.agent2_model.get()

        self.conversation_text.delete("1.0", tk.END)
        self.add_message(MSG_SYSTEM, f"=== A2A対話開始 ===\n初期プロンプト: {initial_prompt}")
        self.add_message(MSG_SYSTEM, f"Agent1: {agent1_model} | Agent2: {agent2_model}")
        self.add_message(MSG_SYSTEM, f"タイムアウト設定: {self.timeout_setting.get()}秒")

        self.current_thread = threading.Thread(target=self.run_conversation_loop, args=(initial_prompt,), daemon=True)
        self.current_thread.start()

    def _validate_preconditions(self) -> bool:
        """Validates all conditions before starting a conversation."""
        if self.is_running:
            return False

        if not self.input_text.get("1.0", tk.END).strip():
            messagebox.showwarning("警告", "初期プロンプトを入力してください")
            return False

        models = [self.agent1_model.get(), self.agent2_model.get()]
        all_available_models = set(self.available_models) | {name for p in self.API_PROVIDERS.values() if "models" in p for name in p["models"]}

        for i, model_name in enumerate(models):
            if model_name not in all_available_models:
                messagebox.showerror("エラー", f"Agent{i+1}モデル '{model_name}' が見つかりません。")
                return False
            
            provider_name, _ = self._get_model_provider(model_name)
            if provider_name != "Ollama":
                key_var = getattr(self, self.API_PROVIDERS[provider_name]["key_var_name"])
                if not key_var.get():
                    messagebox.showerror("エラー", f"{provider_name} APIキーが設定されていません。")
                    return False
        return True

    def run_conversation_loop(self, initial_prompt: str):
        """The main loop for running the conversation between agents."""
        try:
            current_prompt = initial_prompt
            for round_num in range(self.max_rounds.get()):
                if not self.is_running:
                    self.message_queue.put((MSG_SYSTEM, "⏹ 対話が停止されました。"))
                    break

                self.message_queue.put((MSG_SYSTEM, f"--- ラウンド {round_num + 1}/{self.max_rounds.get()} ---"))

                # Agent 1's turn
                agent1_response = self._run_agent_turn("Agent 1", self.agent1_model.get(), current_prompt)
                if agent1_response is None: break
                
                if not self.is_running:
                    self.message_queue.put((MSG_SYSTEM, "⏹ 対話が停止されました。"))
                    break

                # Add a cooldown period to avoid rate limiting
                time.sleep(2)

                # Agent 2's turn
                agent2_prompt = f"""前のエージェントの意見:

---

{agent1_response}

---

上記の意見を踏まえ、以下のテーマについて評価・批評・改善提案をしてください:

> {initial_prompt}
"""
                agent2_response = self._run_agent_turn("Agent 2", self.agent2_model.get(), agent2_prompt)
                if agent2_response is None: break

                # Prepare for the next round
                current_prompt = f"""これまでの議論の要約:

**Agent 1 (分析役)の意見:**
```text
{agent1_response}
```

**Agent 2 (評価役)の意見:**
```text
{agent2_response}
```

上記の議論を踏まえ、以下のテーマについてさらに深く考察を続けてください:

> {initial_prompt}
"""

            if self.is_running:
                self.message_queue.put((MSG_SYSTEM, "=== 対話終了 ==="))

        except Exception as e:
            error_message = f"予期しないエラーが発生しました: {e}\n\n詳細:\n{traceback.format_exc()}"
            logging.error(error_message)
            self.message_queue.put((MSG_ERROR, "予期しないエラーが発生しました。ログファイルを確認してください。"))
        finally:
            self.message_queue.put((MSG_FINISHED, None))

    def _run_agent_turn(self, agent_name: str, model_name: str, prompt: str) -> Optional[str]:
        """Executes a single turn for one agent."""
        self.message_queue.put((MSG_SYSTEM, f"{agent_name} ({model_name}) 思考中..."))
        start_time = time.time()

        # Add instruction for Japanese response
        japanese_instruction = "以下の質問には必ず日本語で回答してください。\n\n"
        modified_prompt = japanese_instruction + prompt
        
        response = self._query_model_with_progress(model_name, modified_prompt, agent_name)
        
        if response is None:
            elapsed = time.time() - start_time
            self.message_queue.put((MSG_ERROR, f"{agent_name}の応答でエラーが発生しました（{elapsed:.1f}秒経過）。対話を終了します。"))
            return None

        msg_type = MSG_AGENT1 if agent_name == "Agent 1" else MSG_AGENT2
        self.message_queue.put((msg_type, f"🤖 {agent_name}: {response}"))
        return response

    def stop_conversation(self):
        """Stops the currently running conversation."""
        if not self.is_running:
            return
            
        self.is_running = False
        if self.current_thread and self.current_thread.is_alive():
            self.current_thread.join(timeout=1.0)
            
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.progress.stop()
        self.status_label.config(text="対話停止")

    def clear_conversation(self):
        """Clears the conversation text area."""
        self.conversation_text.delete("1.0", tk.END)
        self.status_label.config(text="対話ログをクリアしました")

    # --- Model Interaction ---

    def _get_model_provider(self, model_name: str) -> Tuple[str, Dict[str, Any]]:
        """Gets the provider information for a given model name."""
        if model_name.startswith("OpenRouter Model"):
            return "OpenRouter", self.API_PROVIDERS["OpenRouter"]

        # First, check if it's an Ollama model
        if model_name in self.available_models:
            return "Ollama", self.API_PROVIDERS["Ollama"]

        # If not an Ollama model, check if it's an API model
        for provider, details in self.API_PROVIDERS.items():
            if provider != "Ollama" and "models" in details and model_name in details["models"]:
                return provider, details
        
        # Fallback (should ideally not be reached if models are correctly populated)
        # This might indicate an invalid model name selected
        raise ValueError(f"不明なモデル名です: {model_name}")

    def _query_model_with_progress(self, model_name: str, prompt: str, agent_name: str) -> Optional[str]:
        """Queries a model with a background progress updater."""
        timeout = self.timeout_setting.get()
        response_queue = queue.Queue()

        def query_target():
            provider_name, provider_details = self._get_model_provider(model_name)
            query_function_name = provider_details["query_func"]
            query_function = getattr(self, query_function_name)

            max_retries = 5
            base_delay = 2  # Start with a 2-second delay

            for attempt in range(max_retries):
                try:
                    if provider_name == "OpenRouter":
                        response = query_function(model_name, prompt)
                    elif provider_name != "Ollama":
                        api_model_id = provider_details["models"][model_name]
                        response = query_function(api_model_id, prompt)
                    else:
                        response = query_function(model_name, prompt)
                    
                    response_queue.put(response)
                    return  # Success

                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 429 and attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        self.message_queue.put((MSG_SYSTEM, f"レート制限: {delay}秒待機して再試行します... ({attempt + 1}/{max_retries})"))
                        time.sleep(delay)
                    else:
                        logging.error(f"{provider_name} API HTTPエラー: {e}\n{traceback.format_exc()}")
                        self.message_queue.put((MSG_ERROR, f"{provider_name} APIでHTTPエラーが発生しました。"))
                        response_queue.put(None)
                        return
                except ValueError as ve:
                    logging.error(f"モデルプロバイダーの特定エラー: {ve}\n{traceback.format_exc()}")
                    self.message_queue.put((MSG_ERROR, f"モデルプロバイダーの特定エラーが発生しました。"))
                    response_queue.put(None)
                    return
                except Exception as e:
                    # Catch other potential errors like connection errors on retries
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        self.message_queue.put((MSG_SYSTEM, f"一時的なエラー: {delay}秒待機して再試行します... ({attempt + 1}/{max_retries})"))
                        time.sleep(delay)
                    else:
                        logging.error(f"{provider_name} APIエラー: {e}\n{traceback.format_exc()}")
                        self.message_queue.put((MSG_ERROR, f"{provider_name} APIでエラーが発生しました。"))
                        response_queue.put(None)
                        return
            
            # If all retries fail
            self.message_queue.put((MSG_ERROR, f"{provider_name} APIの再試行がすべて失敗しました。"))
            response_queue.put(None)

        query_thread = threading.Thread(target=query_target, daemon=True)
        query_thread.start()

        start_time = time.time()
        while query_thread.is_alive():
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                self.message_queue.put((MSG_ERROR, f"タイムアウト（{timeout}秒）が発生しました。"))
                return None
            
            remaining = timeout - elapsed
            self.status_label.config(text=f"{agent_name} 思考中... ({remaining:.0f}秒残り)")
            time.sleep(0.1)
        
        return response_queue.get()

    def _query_gemini(self, api_model_id: str, prompt: str) -> Optional[str]:
        """Queries the Gemini API."""
        api_key = self.gemini_api_key.get()
        if not api_key:
            raise ValueError("Gemini APIキーが設定されていません。")
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(api_model_id)
        response = model.generate_content(prompt)
        return response.text

    def _query_claude(self, model_id: str, prompt: str) -> Optional[str]:
        """Queries the Claude API."""
        api_key = self.claude_api_key.get()
        if not api_key:
            raise ValueError("Claude APIキーが設定されていません。")

        client = anthropic.Anthropic(api_key=api_key, timeout=60.0)
        message = client.messages.create(
            model=model_id,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text

    def _query_openrouter(self, model_id: str, prompt: str) -> Optional[str]:
        """Queries the OpenRouter API."""
        api_key = self.openrouter_api_key.get()
        if not api_key:
            raise ValueError("OpenRouter APIキーが設定されていません。")
        
        if model_id == "OpenRouter Model 1":
            model_name = self.openrouter_model_1_name.get()
        elif model_id == "OpenRouter Model 2":
            model_name = self.openrouter_model_2_name.get()
        else:
            raise ValueError(f"無効なOpenRouterモデルIDです: {model_id}")

        if not model_name:
            raise ValueError("OpenRouterのモデル名が設定されていません。")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}]
        }
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=self.timeout_setting.get())
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def _query_ollama(self, model: str, prompt: str) -> Optional[str]:
        """Queries the Ollama API."""
        try:
            data = {
                "model": model, "prompt": prompt, "stream": False,
                "options": {"temperature": 0.7, "top_p": 0.9, "num_ctx": 10000, "num_predict": 10000}
            }
            response = requests.post(f"{self.ollama_url}/api/generate", json=data, timeout=self.timeout_setting.get())
            response.raise_for_status()
            json_response = response.json()
            if "response" in json_response:
                return json_response["response"]
            else:
                error_msg = f"Ollamaからの応答に'response'キーがありません。完全な応答: {json_response}"
                logging.error(error_msg)
                raise ValueError(error_msg)
        except requests.exceptions.Timeout:
            error_msg = f"Ollamaへの接続がタイムアウトしました ({self.timeout_setting.get()}秒)"
            logging.error(error_msg)
            raise TimeoutError(error_msg)
        except requests.exceptions.ConnectionError:
            error_msg = "Ollamaサービスに接続できません。'ollama serve'を確認してください。"
            logging.error(error_msg)
            raise ConnectionError(error_msg)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                error_msg = f"モデル '{model}' が見つかりません (404エラー)"
                logging.error(error_msg)
                raise FileNotFoundError(error_msg)
            error_msg = f"Ollama APIエラー: {e.response.status_code} - {e.response.text}"
            logging.error(error_msg)
            raise IOError(error_msg)

    # --- Ollama & Model Management ---

    def check_ollama_status(self):
        """Checks the status of the Ollama service and gets available models."""
        def check_in_thread():
            try:
                response = requests.get(f"{self.ollama_url}/api/tags", timeout=10)
                response.raise_for_status()
                data = response.json()
                models = [model['name'] for model in data.get('models', [])]
                self.message_queue.put((MSG_STATUS_OK, f"✅ Ollama接続OK ({len(models)}個のモデル)"))
                self.message_queue.put((MSG_MODELS, models))
            except requests.RequestException:
                self.message_queue.put((MSG_STATUS_ERROR, "❌ Ollama未起動 - 'ollama serve'を実行してください"))
        
        threading.Thread(target=check_in_thread, daemon=True).start()

    def check_ollama_status_sync_and_show_popup(self):
        """Synchronously checks Ollama status and shows a popup with the result."""
        parent_dialog = self.root.focus_get() or self.root

        try:
            self.status_label.config(text="Ollamaをチェックしています...")
            self.root.update_idletasks()
            
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            response.raise_for_status()
            data = response.json()
            models = [model['name'] for model in data.get('models', [])]
            msg = f"✅ Ollama接続OK ({len(models)}個のモデルが見つかりました)"
            
            self.message_queue.put((MSG_STATUS_OK, msg))
            self.message_queue.put((MSG_MODELS, models))
            messagebox.showinfo("Ollama ステータス", msg, parent=parent_dialog)

        except requests.exceptions.Timeout:
            msg = "❌ Ollamaへの接続がタイムアウトしました (5秒)。"
            self.message_queue.put((MSG_STATUS_ERROR, msg))
            messagebox.showerror("Ollama ステータス", msg, parent=parent_dialog)
        except requests.exceptions.ConnectionError:
            msg = "❌ Ollamaサービスに接続できません。'ollama serve'が実行されているか確認してください。"
            self.message_queue.put((MSG_STATUS_ERROR, msg))
            messagebox.showerror("Ollama ステータス", msg, parent=parent_dialog)
        except requests.exceptions.RequestException as e:
            msg = f"❌ Ollamaへの接続中にエラーが発生しました: {e}"
            self.message_queue.put((MSG_STATUS_ERROR, msg))
            messagebox.showerror("Ollama ステータス", msg, parent=parent_dialog)

    def update_model_combos(self, ollama_models: List[str]):
        """Updates the model selection comboboxes with available models."""
        api_models = [name for p_name, p_details in self.API_PROVIDERS.items() if "models" in p_details for name in p_details["models"]]
        full_model_list = sorted(ollama_models) + sorted(api_models)

        if self.agent1_combo and self.agent2_combo:
            self.agent1_combo['values'] = full_model_list
            self.agent2_combo['values'] = full_model_list
            
            if full_model_list:
                self.agent1_model.set(full_model_list[0])
                self.agent2_model.set(full_model_list[1] if len(full_model_list) > 1 else full_model_list[0])

    # --- File & Sound Operations ---

    def save_conversation(self):
        """Saves the conversation log to a Markdown file."""
        content = self.conversation_text.get("1.0", tk.END)
        if not content.strip():
            messagebox.showinfo("情報", "保存する内容がありません")
            return

        default_filename = f"ollama_a2a_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".md",
            filetypes=[("Markdownファイル", "*.md"), ("テキストファイル", "*.txt")],
            initialfile=default_filename,
            title="対話ログを保存"
        )
        
        if not filepath:
            return
            
        try:
            markdown_content = self._format_as_markdown(content)
            Path(filepath).write_text(markdown_content, encoding='utf-8')
            messagebox.showinfo("成功", f"ファイルを保存しました:\n{filepath}")
            self.status_label.config(text=f"保存完了: {Path(filepath).name}")
        except Exception as e:
            messagebox.showerror("エラー", f"保存に失敗しました:\n{e}")

    def _format_as_markdown(self, content: str) -> str:
        """Formats the raw text content from the UI into Markdown."""
        # Remove <think>...</think> blocks first
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)

        lines = content.split('\n')
        markdown_lines = [
            "# Ollama A2A 対話ログ",
            f"生成日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}",
            ""
        ]
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            content_part = line.split("] ", 1)[1] if "] " in line else line
            
            if content_part.startswith("🤖 Agent 1:"):
                markdown_lines.extend(["## Agent 1 (分析役)", f"> {content_part[12:].strip()}", ""])
            elif content_part.startswith("🤖 Agent 2:"):
                markdown_lines.extend(["## Agent 2 (評価役)", f"> {content_part[12:].strip()}", ""])
            elif content_part.startswith("=== "):
                markdown_lines.extend([f"## {content_part}", ""])
            elif content_part.startswith("--- "):
                markdown_lines.extend([f"### {content_part}", ""])
            elif content_part.startswith("❌") or content_part.startswith("⚠️"):
                markdown_lines.extend([f"**{content_part}**", ""])
            else:
                markdown_lines.append(content_part)
        
        return '\n'.join(markdown_lines)

    def play_bell_sound(self):
        """Plays a notification sound once per conversation."""
        if self.sound_played:
            return
        if not self.bell_sound_path.exists() or self.bell_sound_path.stat().st_size < 100:
            logging.error(f"音声ファイルが見つからないか、破損しています: {self.bell_sound_path}")
            return

        def play_in_thread():
            command = self._get_sound_command()
            if command is None:
                logging.error(f"サポートされていないOSです: {sys.platform}")
                return

            try:
                if isinstance(command, str) and command == "pygame":
                    self._play_sound_pygame()
                else:
                    subprocess.run(command, check=True, capture_output=True, text=True, timeout=10)
                
                self.sound_played = True
                self.message_queue.put((MSG_SYSTEM, "🔔 対話終了のお知らせ音を再生しました\n"))
            except Exception as e:
                logging.error(f"音声再生エラー: {e}\n{traceback.format_exc()}")
                self.message_queue.put((MSG_ERROR, "音声再生エラーが発生しました。ログファイルを確認してください。"))

        threading.Thread(target=play_in_thread, daemon=True).start()

    def _get_sound_command(self) -> Optional[List[str] or str]:
        """Gets the appropriate sound playing command based on the OS."""
        if sys.platform == "darwin":
            return ["afplay", str(self.bell_sound_path)]
        elif sys.platform.startswith("linux"):
            if subprocess.run(["which", "aplay"], capture_output=True).returncode == 0:
                return ["aplay", str(self.bell_sound_path)]
            if subprocess.run(["which", "paplay"], capture_output=True).returncode == 0:
                return ["paplay", str(self.bell_sound_path)]
        elif sys.platform == "win32":
            try:
                import pygame
                return "pygame"
            except ImportError:
                return ["powershell", "-c", f"(New-Object Media.SoundPlayer \"{self.bell_sound_path}\").PlaySync()"]
        return None

    def _play_sound_pygame(self):
        """Plays sound using the pygame library."""
        import pygame
        try:
            pygame.mixer.init()
            pygame.mixer.music.load(str(self.bell_sound_path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
        finally:
            if pygame.mixer.get_init():
                pygame.mixer.quit()

    def test_audio_system(self):
        """Tests the audio system and reports the results."""
        command = self._get_sound_command()
        if command:
            messagebox.showinfo("音声システム テスト結果", f"✅ コマンドが見つかりました: {' '.join(command) if isinstance(command, list) else command}")
        else:
            messagebox.showerror("音声システム テスト結果", f"❌ 音声再生コマンドが見つかりません (OS: {sys.platform})")

    # --- Queue & UI Updates ---

    def add_message(self, msg_type: str, content: str):
        """Adds a formatted message to the conversation text area."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.conversation_text.insert(tk.END, f"[{timestamp}] ", TAG_TIMESTAMP)
        self.conversation_text.insert(tk.END, f"{content}\n", msg_type)
        self.conversation_text.see(tk.END)

    def check_queue(self):
        """Checks the message queue and updates the UI accordingly."""
        try:
            while True:
                msg_type, content = self.message_queue.get_nowait()
                
                if msg_type == MSG_STATUS_OK or msg_type == MSG_STATUS_ERROR or msg_type == MSG_PROGRESS:
                    self.status_label.config(text=content)
                elif msg_type == MSG_MODELS:
                    self.available_models = content
                    self.update_model_combos(content)
                elif msg_type == MSG_FINISHED:
                    self.stop_conversation()
                    self.play_bell_sound()
                elif msg_type == MSG_ERROR:
                    self.add_message(TAG_ERROR, f"❌ {content}")
                else:
                    self.add_message(msg_type, content)
                    
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.check_queue)

# --- Application Entry Point ---

def main():
    """Application entry point."""
    root = tk.Tk()
    app = OllamaA2AApp(root)
    
    def on_closing():
        if app.is_running and messagebox.askokcancel("終了確認", "対話が実行中です。終了しますか？"):
            app.stop_conversation()
            root.destroy()
        elif not app.is_running:
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()