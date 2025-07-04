#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ollama A2A Desktop App for macOS
軽量なAgent-to-Agent通信デスクトップアプリケーション
改善版：タイムアウト対応と.md保存対応, Gemini API連携追加
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog, simpledialog
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
import google.generativeai as genai
import anthropic
import certifi

# SSL証明書のパスを設定
os.environ["SSL_CERT_FILE"] = certifi.where()


class OllamaA2AApp:
    GEMINI_MODEL_NAME = "Gemini 2.5 Pro (API)"
    GEMINI_FLASH_MODEL_NAME = "Gemini 2.5 Flash (API)"
    CLAUDE_3_OPUS_MODEL_NAME = "Claude 3 Opus (API)"
    CLAUDE_3_SONNET_MODEL_NAME = "Claude 3 Sonnet (API)"
    CLAUDE_3_HAIKU_MODEL_NAME = "Claude 3 Haiku (API)"

    def __init__(self, root):
        self.root = root
        self.message_queue = queue.Queue() # Moved to the top
        self.setup_window()
        self.setup_variables()
        self.setup_ui()
        self.setup_ollama_connection()
        self.check_queue()

    def setup_window(self):
        """ウィンドウの基本設定"""
        self.root.title("Ollama A2A - Agent to Agent Communication")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)
        
        # macOSスタイルの設定
        style = ttk.Style()
        if sys.platform == "darwin":
            style.theme_use("aqua")

    def setup_variables(self):
        """変数の初期化"""
        self.ollama_url = "http://localhost:11434"
        self.available_models = []
        self.current_conversation = []
        self.is_running = False
        self.current_thread = None
        
        # 設定可能な変数
        self.agent1_model = tk.StringVar(value="hf.co/Menlo/Jan-nano-gguf:Q4_K_M")
        self.agent2_model = tk.StringVar(value="sam860/deepseek-r1-0528-qwen3:8b")
        self.max_rounds = tk.IntVar(value=3)
        self.auto_mode = tk.BooleanVar(value=False)
        self.timeout_setting = tk.IntVar(value=600)  # デフォルト10分
        self.gemini_api_key = tk.StringVar()
        self.claude_api_key = tk.StringVar()

        # コンボボックスの参照を保存
        self.agent1_combo = None
        self.agent2_combo = None
        
        # 音声再生関連の変数
        self.sound_played = False  # 重複再生防止フラグ
        self.bell_sound_path = Path(__file__).parent.parent / "bell.mp3"
        self.gemini_api_key_path = Path(__file__).parent.parent / ".gemini_api_key"
        self.claude_api_key_path = Path(__file__).parent.parent / ".claude_api_key"
        
        # APIキーをファイルから読み込む
        self.load_api_key(self.gemini_api_key_path, self.gemini_api_key, "Gemini")
        self.load_api_key(self.claude_api_key_path, self.claude_api_key, "Claude")

    def load_api_key(self, path, var, name):
        if path.exists():
            try:
                with open(path, 'r') as f:
                    key = f.read().strip()
                    if key:
                        var.set(key)
                        self.message_queue.put(("status_ok", f"✅ {name} APIキー自動読み込み済み"))
            except Exception as e:
                self.message_queue.put(("error", f"{name} APIキーファイルの読み込みエラー: {e}"))

    def setup_ui(self):
        """UIの構築"""
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # ウィンドウのリサイズ設定
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(3, weight=1)

        # タイトル
        title_label = ttk.Label(main_frame, text="🤖 Ollama A2A Communication", 
                               font=("SF Pro Display", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        # 設定パネル
        self.create_settings_panel(main_frame)
        
        # 入力パネル
        self.create_input_panel(main_frame)
        
        # 会話表示パネル
        self.create_conversation_panel(main_frame)
        
        # 制御パネル
        self.create_control_panel(main_frame)
        
        # ステータスバー
        self.create_status_bar(main_frame)

    def create_settings_panel(self, parent):
        """設定パネルの作成"""
        settings_frame = ttk.LabelFrame(parent, text="⚙️ エージェント設定", padding="10")
        settings_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        settings_frame.columnconfigure(1, weight=1)
        settings_frame.columnconfigure(3, weight=1)

        # Agent 1設定
        ttk.Label(settings_frame, text="Agent 1 (分析役):").grid(row=0, column=0, padx=(0, 10))
        self.agent1_combo = ttk.Combobox(settings_frame, textvariable=self.agent1_model)
        self.agent1_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 20))

        # Agent 2設定
        ttk.Label(settings_frame, text="Agent 2 (評価役):").grid(row=0, column=2, padx=(0, 10))
        self.agent2_combo = ttk.Combobox(settings_frame, textvariable=self.agent2_model)
        self.agent2_combo.grid(row=0, column=3, sticky=(tk.W, tk.E))

        # 詳細設定
        ttk.Label(settings_frame, text="対話ラウンド数:").grid(row=1, column=0, padx=(0, 10), pady=(10, 0))
        rounds_spin = ttk.Spinbox(settings_frame, from_=1, to=10, textvariable=self.max_rounds, width=10)
        rounds_spin.grid(row=1, column=1, sticky=(tk.W), padx=(0, 20), pady=(10, 0))

        ttk.Label(settings_frame, text="タイムアウト(秒):").grid(row=1, column=2, padx=(0, 10), pady=(10, 0))
        timeout_spin = ttk.Spinbox(settings_frame, from_=60, to=600, textvariable=self.timeout_setting, width=10)
        timeout_spin.grid(row=1, column=3, sticky=(tk.W), pady=(10, 0))

        auto_check = ttk.Checkbutton(settings_frame, text="自動連続実行", variable=self.auto_mode)
        auto_check.grid(row=2, column=0, columnspan=2, sticky=(tk.W), pady=(10, 0))

        # Gemini APIキー設定ボタン
        settings_button = ttk.Button(settings_frame, text="⚙️ 設定", command=self.open_settings_dialog)
        settings_button.grid(row=3, column=0, columnspan=4, sticky=(tk.W), pady=(10, 0))

    def create_input_panel(self, parent):
        """入力パネルの作成"""
        input_frame = ttk.LabelFrame(parent, text="💭 初期プロンプト", padding="10")
        input_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        input_frame.columnconfigure(0, weight=1)
        input_frame.rowconfigure(0, weight=1)

        # テキスト入力エリアとスクロールバーのコンテナ
        text_container = ttk.Frame(input_frame)
        text_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        text_container.columnconfigure(0, weight=1)
        text_container.rowconfigure(0, weight=1)

        self.input_text = tk.Text(text_container, height=4, wrap=tk.WORD)
        self.input_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.input_text.insert("1.0", "AIの未来について議論してください。技術的な可能性と社会的な影響の両面から考察してください。")

        # スクロールバー
        input_scrollbar = ttk.Scrollbar(text_container, orient="vertical", command=self.input_text.yview)
        input_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.input_text.configure(yscrollcommand=input_scrollbar.set)

        # ヒントラベル（右下に配置）
        hint_label = ttk.Label(input_frame, text="💡 Shift+Enter で対話開始", 
                              font=("SF Pro Display", 9), foreground="#666666")
        hint_label.grid(row=1, column=0, sticky=(tk.E), pady=(5, 0))

        # キーバインディングの設定
        self.input_text.bind('<Shift-Return>', self.on_shift_enter)
        self.input_text.bind('<Control-Return>', self.on_shift_enter)  # Ctrl+Enterも対応（Linux対応）

    def create_conversation_panel(self, parent):
        """会話表示パネルの作成"""
        conv_frame = ttk.LabelFrame(parent, text="💬 エージェント間対話", padding="10")
        conv_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        conv_frame.columnconfigure(0, weight=1)
        conv_frame.rowconfigure(0, weight=1)

        self.conversation_text = scrolledtext.ScrolledText(conv_frame, wrap=tk.WORD, 
                                                          font=("Monaco", 11))
        self.conversation_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # タグ設定（色分け用）
        self.conversation_text.tag_config("agent1", foreground="#0066CC", font=("Monaco", 11, "bold"))
        self.conversation_text.tag_config("agent2", foreground="#CC6600", font=("Monaco", 11, "bold"))
        self.conversation_text.tag_config("system", foreground="#666666", font=("Monaco", 10, "italic"))
        self.conversation_text.tag_config("timestamp", foreground="#999999", font=("Monaco", 9))
        self.conversation_text.tag_config("error", foreground="#CC0000", font=("Monaco", 10, "bold"))

    def create_control_panel(self, parent):
        """制御パネルの作成"""
        control_frame = ttk.Frame(parent)
        control_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        control_frame.columnconfigure(1, weight=1)

        # ボタン群
        self.start_button = ttk.Button(control_frame, text="🚀 対話開始", 
                                      command=self.start_conversation, style="Accent.TButton")
        self.start_button.grid(row=0, column=0, padx=(0, 10))

        self.stop_button = ttk.Button(control_frame, text="⏹ 停止", 
                                     command=self.stop_conversation, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=(0, 10))

        self.clear_button = ttk.Button(control_frame, text="🗑 クリア", 
                                      command=self.clear_conversation)
        self.clear_button.grid(row=0, column=2, padx=(0, 10))

        self.save_button = ttk.Button(control_frame, text="💾 保存(.md)", 
                                     command=self.save_conversation)
        self.save_button.grid(row=0, column=3, padx=(0, 10))

        

    def create_status_bar(self, parent):
        """ステータスバーの作成"""
        status_frame = ttk.Frame(parent)
        status_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E))
        status_frame.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(status_frame, text="準備完了 - Ollamaサービスを確認してください")
        self.status_label.grid(row=0, column=0, sticky=(tk.W))

        # プログレスバー
        self.progress = ttk.Progressbar(status_frame, mode='indeterminate')
        self.progress.grid(row=0, column=1, sticky=(tk.E), padx=(10, 0))

    def setup_ollama_connection(self):
        """Ollama接続の初期設定"""
        self.check_ollama_status()

    def check_ollama_status(self):
        """Ollamaサービスの状態確認（改善版）"""
        def check_status():
            try:
                response = requests.get(f"{self.ollama_url}/api/tags", timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    models = [model['name'] for model in data.get('models', [])]
                    self.available_models = models
                    self.message_queue.put(("status_ok", f"✅ Ollama接続OK ({len(models)}個のモデル)"))
                    self.message_queue.put(("models", models))
                    
                    # モデル名の検証と推奨表示
                    self.message_queue.put(("model_validation", models))
                else:
                    self.message_queue.put(("status_error", "❌ Ollama応答エラー"))
            except requests.exceptions.RequestException:
                self.message_queue.put(("status_error", "❌ Ollama未起動 - 'ollama serve'を実行してください"))

        threading.Thread(target=check_status, daemon=True).start()

    def open_settings_dialog(self):
        """Gemini APIキー設定ダイアログを開く"""
        dialog = tk.Toplevel(self.root)
        dialog.title("APIキー設定")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.focus_set()
        
        # ダイアログのサイズと位置を調整
        dialog_width = 450
        dialog_height = 500
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = int((screen_width / 2) - (dialog_width / 2))
        y = int((screen_height / 2) - (dialog_height / 2))
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        dialog.resizable(False, False) # サイズ変更不可

        dialog_frame = ttk.Frame(dialog, padding="20")
        dialog_frame.pack(fill=tk.BOTH, expand=True)
        dialog_frame.columnconfigure(1, weight=1)

        # API Key Section
        api_frame = ttk.LabelFrame(dialog_frame, text="🔑 API設定", padding="10")
        api_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        api_frame.columnconfigure(1, weight=1)

        # Gemini
        gemini_frame = ttk.LabelFrame(api_frame, text="Gemini API設定", padding="10")
        gemini_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        gemini_frame.columnconfigure(1, weight=1)
        ttk.Label(gemini_frame, text="API Key:").grid(row=0, column=0, padx=(0, 10), pady=(5, 0), sticky=tk.W)
        gemini_api_key_entry = ttk.Entry(gemini_frame, show="*", width=40)
        gemini_api_key_entry.grid(row=0, column=1, padx=(0, 0), pady=(5, 0), sticky=(tk.W, tk.E))
        gemini_api_key_entry.insert(0, self.gemini_api_key.get())
        save_gemini_button = ttk.Button(gemini_frame, text="保存 & 検証", command=lambda: self.save_gemini_key(gemini_api_key_entry.get(), dialog))
        save_gemini_button.grid(row=1, column=0, columnspan=2, pady=(10, 0))

        # Claude
        claude_frame = ttk.LabelFrame(api_frame, text="Claude API設定", padding="10")
        claude_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        claude_frame.columnconfigure(1, weight=1)
        ttk.Label(claude_frame, text="API Key:").grid(row=0, column=0, padx=(0, 10), pady=(5, 0), sticky=tk.W)
        claude_api_key_entry = ttk.Entry(claude_frame, show="*", width=40)
        claude_api_key_entry.grid(row=0, column=1, padx=(0, 0), pady=(5, 0), sticky=(tk.W, tk.E))
        claude_api_key_entry.insert(0, self.claude_api_key.get())
        save_claude_button = ttk.Button(claude_frame, text="保存 & 検証", command=lambda: self.save_claude_key(claude_api_key_entry.get(), dialog))
        save_claude_button.grid(row=1, column=0, columnspan=2, pady=(10, 0))

        # Test Buttons Section
        test_frame = ttk.LabelFrame(dialog_frame, text="🛠️ テストと確認", padding="10")
        test_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        test_frame.columnconfigure(0, weight=1)
        test_frame.columnconfigure(1, weight=1)

        ollama_check_button = ttk.Button(test_frame, text="🔍 Ollama確認", command=self.check_ollama_status)
        ollama_check_button.grid(row=0, column=0, padx=(0, 5), pady=(5, 0), sticky=(tk.W, tk.E))

        audio_test_button = ttk.Button(test_frame, text="🔊 音声テスト", command=self.test_audio_system)
        audio_test_button.grid(row=0, column=1, padx=(5, 0), pady=(5, 0), sticky=(tk.W, tk.E))

        # Close Button
        close_button = ttk.Button(dialog_frame, text="閉じる", command=dialog.destroy)
        close_button.grid(row=3, column=0, columnspan=2, pady=(20, 0))

        dialog.wait_window(dialog)

    def save_gemini_key(self, key, dialog=None):
        """Gemini APIキーを検証し、ファイルに保存する"""
        if not key:
            messagebox.showwarning("警告", "Gemini APIキーが入力されていません", parent=dialog)
            return
        try:
            genai.configure(api_key=key)
            genai.get_model('models/gemini-1.5-pro-latest') # テスト
            with open(self.gemini_api_key_path, 'w') as f:
                f.write(key)
            self.gemini_api_key.set(key)
            messagebox.showinfo("成功", "Gemini APIキーが正常に保存されました", parent=dialog)
            self.message_queue.put(("status_ok", "✅ Gemini APIキー設定済み"))
        except Exception as e:
            messagebox.showerror("エラー", f"Gemini APIキーの検証に失敗しました: {e}", parent=dialog)

    def save_claude_key(self, key, dialog=None):
        """Claude APIキーを検証し、ファイルに保存する"""
        print(f"DEBUG: save_claude_key called with key (first 5 chars): {key[:5]}...")
        if not key:
            messagebox.showwarning("警告", "Claude APIキーが入力されていません", parent=dialog)
            print("DEBUG: Claude API key is empty.")
            return
        try:
            print("DEBUG: Initializing anthropic.Anthropic client...")
            client = anthropic.Anthropic(api_key=key, timeout=60.0)
            print("DEBUG: Client initialized. Testing models.list()...")
            client.models.list() # テスト
            print("DEBUG: models.list() successful. Saving key to file...")
            with open(self.claude_api_key_path, 'w') as f:
                f.write(key)
            self.claude_api_key.set(key)
            print("DEBUG: Claude API key saved successfully.")
            messagebox.showinfo("成功", "Claude APIキーが正常に保存されました", parent=dialog)
            self.message_queue.put(("status_ok", "✅ Claude APIキー設定済み"))
        except anthropic.AuthenticationError as auth_e:
            print(f"DEBUG: AuthenticationError occurred: {auth_e}")
            messagebox.showerror("認証エラー", "Claude APIキーが無効です。キーを確認して再試行してください。", parent=dialog)
        except Exception as e:
            error_type = type(e).__name__
            print(f"DEBUG: An unexpected error occurred: {error_type} - {e}")
            messagebox.showerror("エラー", f"Claude APIキーの検証に失敗しました。エラー種別: {error_type}", parent=dialog)

    def update_model_combos(self, available_models):
        """モデルコンボボックスを実際のモデルで更新"""
        
        # OllamaモデルのリストにAPIモデルを追加
        full_model_list = [
            self.GEMINI_MODEL_NAME, 
            self.GEMINI_FLASH_MODEL_NAME,
            self.CLAUDE_3_OPUS_MODEL_NAME,
            self.CLAUDE_3_SONNET_MODEL_NAME,
            self.CLAUDE_3_HAIKU_MODEL_NAME,
        ] + available_models

        if self.agent1_combo and self.agent2_combo:
            self.agent1_combo['values'] = full_model_list
            self.agent2_combo['values'] = full_model_list
            
            # デフォルト値の設定
            if available_models:
                self.agent1_model.set(available_models[0])
            else:
                self.agent1_model.set(self.GEMINI_MODEL_NAME)
            self.agent2_model.set(self.CLAUDE_3_SONNET_MODEL_NAME) # 修正: CLAUDE_3_SONPUS_MODEL_NAME -> CLAUDE_3_SONNET_MODEL_NAME

    def validate_models(self, available_models):
        """選択されたモデルが利用可能かチェック"""
        agent1 = self.agent1_model.get()
        agent2 = self.agent2_model.get()

        messages = []

        # Agent1のチェック
        if agent1 in (self.GEMINI_MODEL_NAME, self.GEMINI_FLASH_MODEL_NAME, self.CLAUDE_3_OPUS_MODEL_NAME, self.CLAUDE_3_SONNET_MODEL_NAME, self.CLAUDE_3_HAIKU_MODEL_NAME):
            messages.append(f"✅ Agent1モデル '{agent1}' 利用可能 (API)")
        elif agent1 not in self.available_models: # 修正: (self.GEMINI_MODEL_NAME, self.GEMINI_FLASH_MODEL_NAME) のチェックを削除
            messages.append(f"⚠️ Agent1モデル '{agent1}' が見つかりません")
        else:
            messages.append(f"✅ Agent1モデル '{agent1}' 利用可能")

        # Agent2のチェック
        if agent2 in (self.GEMINI_MODEL_NAME, self.GEMINI_FLASH_MODEL_NAME, self.CLAUDE_3_OPUS_MODEL_NAME, self.CLAUDE_3_SONNET_MODEL_NAME, self.CLAUDE_3_HAIKU_MODEL_NAME):
            messages.append(f"✅ Agent2モデル '{agent2}' 利用可能 (API)")
        elif agent2 not in self.available_models: # 修正: (self.GEMINI_MODEL_NAME, self.GEMINI_FLASH_MODEL_NAME) のチェックを削除
            messages.append(f"⚠️ Agent2モデル '{agent2}' が見つかりません")
        else:
            messages.append(f"✅ Agent2モデル '{agent2}' 利用可能")
        # 利用可能なモデル一覧を表示
        messages.append("📋 利用可能なモデル:")
        for model in available_models:
            messages.append(f"  • {model}")
        
        validation_msg = "".join(messages)
        self.message_queue.put(("system", validation_msg + ""))

    def on_shift_enter(self, event):
        """Shift+Enter キーイベントハンドラー"""
        # イベントを消費してデフォルトの改行動作を防ぐ
        self.start_conversation()
        return "break"

    def start_conversation(self):
        """A2A対話の開始（改善版）"""
        if self.is_running:
            return

        initial_prompt = self.input_text.get("1.0", tk.END).strip()
        if not initial_prompt:
            messagebox.showwarning("警告", "初期プロンプトを入力してください")
            return

        agent1_model = self.agent1_model.get()
        agent2_model = self.agent2_model.get()

        # モデルの存在確認（Ollamaモデルのみ）
        # APIモデルはavailable_modelsに含まれないため、別途チェック
        agent1_is_api_model = agent1_model in (self.GEMINI_MODEL_NAME, self.GEMINI_FLASH_MODEL_NAME, self.CLAUDE_3_OPUS_MODEL_NAME, self.CLAUDE_3_SONNET_MODEL_NAME, self.CLAUDE_3_HAIKU_MODEL_NAME)
        agent2_is_api_model = agent2_model in (self.GEMINI_MODEL_NAME, self.GEMINI_FLASH_MODEL_NAME, self.CLAUDE_3_OPUS_MODEL_NAME, self.CLAUDE_3_SONNET_MODEL_NAME, self.CLAUDE_3_HAIKU_MODEL_NAME)

        if not agent1_is_api_model and agent1_model not in self.available_models:
            messagebox.showerror("エラー", f"Agent1モデル '{agent1_model}' が見つかりません。")
            return
            
        if not agent2_is_api_model and agent2_model not in self.available_models:
            messagebox.showerror("エラー", f"Agent2モデル '{agent2_model}' が見つかりません。")
            return

        agent1_is_gemini = agent1_model in (self.GEMINI_MODEL_NAME, self.GEMINI_FLASH_MODEL_NAME)
        agent2_is_gemini = agent2_model in (self.GEMINI_MODEL_NAME, self.GEMINI_FLASH_MODEL_NAME)
        agent1_is_claude = agent1_model in (self.CLAUDE_3_OPUS_MODEL_NAME, self.CLAUDE_3_SONNET_MODEL_NAME, self.CLAUDE_3_HAIKU_MODEL_NAME)
        agent2_is_claude = agent2_model in (self.CLAUDE_3_OPUS_MODEL_NAME, self.CLAUDE_3_SONNET_MODEL_NAME, self.CLAUDE_3_HAIKU_MODEL_NAME)

        if (agent1_is_gemini or agent2_is_gemini) and not self.gemini_api_key.get():
            messagebox.showerror("エラー", "Gemini APIキーが設定されていません。")
            return
        
        if (agent1_is_claude or agent2_is_claude) and not self.claude_api_key.get():
            messagebox.showerror("エラー", "Claude APIキーが設定されていません。")
            return

        self.is_running = True
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.progress.start()
        
        # 音声再生フラグをリセット
        self.sound_played = False

        # 対話ログの初期化
        self.conversation_text.delete("1.0", tk.END)
        self.add_message("system", f"=== A2A対話開始 ===初期プロンプト: {initial_prompt}")
        self.add_message("system", f"Agent1: {agent1_model}　Agent2: {agent2_model}")
        self.add_message("system", f"タイムアウト設定: {self.timeout_setting.get()}秒")

        # バックグラウンドで対話実行
        self.current_thread = threading.Thread(target=self.run_conversation, args=(initial_prompt,), daemon=True)
        self.current_thread.start()

    def run_conversation(self, initial_prompt):
        """A2A対話の実行（Gemini API連携版）"""
        try:
            agent1_model = self.agent1_model.get()
            agent2_model = self.agent2_model.get()
            max_rounds = self.max_rounds.get()

            current_prompt = initial_prompt

            for round_num in range(max_rounds):
                if not self.is_running:
                    self.message_queue.put(("system", "⏹ 対話が停止されました。"))
                    break

                self.message_queue.put(("system", f"--- ラウンド {round_num + 1}/{max_rounds} ---"))

                # Agent 1の応答
                self.message_queue.put(("system", f"Agent 1 ({agent1_model}) 思考中..."))
                start_time = time.time()
                agent1_response = self.query_model_with_progress(agent1_model, current_prompt, "Agent 1")
                
                if agent1_response is None:
                    elapsed = time.time() - start_time
                    self.message_queue.put(("error", f"Agent 1の応答でエラーが発生しました（{elapsed:.1f}秒経過）。対話を終了します。"))
                    break

                self.message_queue.put(("agent1", f"🤖 Agent 1: {agent1_response}"))

                if not self.is_running:
                    self.message_queue.put(("system", "⏹ 対話が停止されました。"))
                    break

                # Agent 2の応答
                agent2_prompt = f"前のエージェントの意見: {agent1_response} この意見について評価・批評・改善提案をしてください: {current_prompt}"
                self.message_queue.put(("system", f"Agent 2 ({agent2_model}) 思考中..."))
                start_time = time.time()
                agent2_response = self.query_model_with_progress(agent2_model, agent2_prompt, "Agent 2")

                if agent2_response is None:
                    elapsed = time.time() - start_time
                    self.message_queue.put(("error", f"Agent 2の応答でエラーが発生しました（{elapsed:.1f}秒経過）。対話を終了します。"))
                    break

                self.message_queue.put(("agent2", f"🤖 Agent 2: {agent2_response}"))

                # 次のラウンドの準備
                current_prompt = f"前回の議論:Agent1: {agent1_response} Agent2: {agent2_response} この議論を踏まえて、さらに深く考察してください: {initial_prompt}"

            if self.is_running:
                self.message_queue.put(("system", "=== 対話終了 ==="))

        except Exception as e:
            self.message_queue.put(("error", f"予期しないエラーが発生しました: {str(e)}"))
        finally:
            self.message_queue.put(("finished", None))

    def query_model_with_progress(self, model, prompt, agent_name):
        """モデルに問い合わせ（プログレス表示付き）"""
        timeout = self.timeout_setting.get()
        start_time = time.time()
        
        def update_progress():
            while self.is_running:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    break
                remaining = timeout - elapsed
                self.message_queue.put(("progress", f"{agent_name} 思考中... ({remaining:.0f}秒残り)"))
                time.sleep(5)
        
        progress_thread = threading.Thread(target=update_progress, daemon=True)
        progress_thread.start()
        
        try:
            if model.strip() in (self.GEMINI_MODEL_NAME, self.GEMINI_FLASH_MODEL_NAME):
                return self.query_gemini(model, prompt)
            elif model.strip() in (self.CLAUDE_3_OPUS_MODEL_NAME, self.CLAUDE_3_SONNET_MODEL_NAME, self.CLAUDE_3_HAIKU_MODEL_NAME):
                return self.query_claude(model, prompt)
            else:
                return self.query_ollama(model, prompt)
        finally:
            pass

    def query_claude(self, model_display_name, prompt):
        """Claude APIに問い合わせ"""
        print(f"DEBUG: query_claude called. Model: {model_display_name}, Prompt (first 50 chars): {prompt[:50]}...")
        try:
            api_key = self.claude_api_key.get()
            if not api_key:
                print("DEBUG: Claude API key is not set.")
                self.message_queue.put(("error", "Claude APIキーが設定されていません。"))
                return None

            print(f"DEBUG: Claude API key (first 5 chars): {api_key[:5]}...")

            if model_display_name == self.CLAUDE_3_OPUS_MODEL_NAME:
                model_id = "claude-3-opus-20240229"
            elif model_display_name == self.CLAUDE_3_SONNET_MODEL_NAME:
                model_id = "claude-3-sonnet-20240229"
            elif model_display_name == self.CLAUDE_3_HAIKU_MODEL_NAME:
                model_id = "claude-3-haiku-20240307"
            else:
                print(f"DEBUG: Unknown Claude model name: {model_display_name}")
                self.message_queue.put(("error", f"不明なClaudeモデル名: {model_display_name}"))
                return None
            
            print(f"DEBUG: Mapped model_display_name '{model_display_name}' to model_id '{model_id}'.")
            print("DEBUG: Initializing anthropic.Anthropic client for query...")
            client = anthropic.Anthropic(api_key=api_key, timeout=60.0)
            print("DEBUG: Client initialized. Calling client.messages.create...")

            message = client.messages.create(
                model=model_id,
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            print(f"DEBUG: client.messages.create successful. Response (first 50 chars): {message.content[0].text[:50]}...")
            return message.content[0].text
        except Exception as e:
            error_type = type(e).__name__
            print(f"DEBUG: Claude API error occurred: {error_type} - {e}")
            self.message_queue.put(("error", f"Claude APIエラー: {str(e)}"))
            return None

    def query_gemini(self, model_display_name, prompt):
        """Gemini APIに問い合わせ"""
        try:
            api_key = self.gemini_api_key.get()
            if not api_key:
                self.message_queue.put(("error", "Gemini APIキーが設定されていません。"))
                return None

            # 表示名からAPIモデルIDを決定
            if model_display_name == self.GEMINI_MODEL_NAME:
                api_model_id = 'gemini-2.5-pro'
            elif model_display_name == self.GEMINI_FLASH_MODEL_NAME:
                api_model_id = 'gemini-2.5-flash'
            else:
                self.message_queue.put(("error", f"不明なGeminiモデル名: {model_display_name}"))
                return None

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(api_model_id)
            response = model.generate_content(prompt)
            
            return response.text
            
        except Exception as e:
            self.message_queue.put(("error", f"Gemini APIエラー: {str(e)}"))
            return None

    def query_ollama(self, model, prompt):
        """Ollamaに問い合わせ（改善版エラーハンドリング）"""
        timeout = self.timeout_setting.get()
        
        try:
            data = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "num_ctx": 2048
                }
            }
            
            response = requests.post(f"{self.ollama_url}/api/generate", json=data, timeout=timeout)
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "応答を取得できませんでした")
            elif response.status_code == 404:
                self.message_queue.put(("error", f"モデル '{model}' が見つかりません (404エラー)"))
                return None
            else:
                self.message_queue.put(("error", f"API Error: {response.status_code} - {response.text}"))
                return None
                
        except requests.exceptions.Timeout:
            self.message_queue.put(("error", f"タイムアウト（{timeout}秒）が発生しました。より軽量なモデルを使用するか、タイムアウト時間を延長してください。"))
            return None
        except requests.exceptions.ConnectionError:
            self.message_queue.put(("error", "Ollamaサービスに接続できません。'ollama serve'が実行されているか確認してください。"))
            return None
        except Exception as e:
            self.message_queue.put(("error", f"通信エラー: {str(e)}"))
            return None

    def stop_conversation(self):
        """対話の停止（改善版）"""
        self.is_running = False
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.progress.stop()
        self.status_label.config(text="対話停止")
        
        # 現在のスレッドが存在する場合は停止を待つ
        if self.current_thread and self.current_thread.is_alive():
            # 最大3秒待機
            for _ in range(30):
                if not self.current_thread.is_alive():
                    break
                time.sleep(0.1)

    def clear_conversation(self):
        """対話ログのクリア"""
        self.conversation_text.delete("1.0", tk.END)
        self.status_label.config(text="対話ログをクリアしました")
    
    def test_audio_system(self):
        """音声システムのテスト"""
        test_results = []
        
        # ファイル存在確認
        if self.bell_sound_path.exists():
            try:
                file_size = self.bell_sound_path.stat().st_size
                test_results.append(f"✅ 音声ファイル存在: {self.bell_sound_path.name} ({file_size} bytes)")
            except OSError as e:
                test_results.append(f"❌ 音声ファイル読み取りエラー: {str(e)}")
        else:
            test_results.append(f"❌ 音声ファイルが見つかりません: {self.bell_sound_path}")
            messagebox.showerror("エラー", "\n".join(test_results))
            return
        
        # OS別コマンド確認
        if sys.platform == "darwin":
            try:
                subprocess.run(["which", "afplay"], check=True, capture_output=True)
                test_results.append("✅ afplayコマンド利用可能")
            except (subprocess.CalledProcessError, FileNotFoundError):
                test_results.append("❌ afplayコマンドが見つかりません")
                
        elif sys.platform.startswith("linux"):
            aplay_available = False
            paplay_available = False
            
            try:
                subprocess.run(["which", "aplay"], check=True, capture_output=True)
                aplay_available = True
                test_results.append("✅ aplayコマンド利用可能")
            except (subprocess.CalledProcessError, FileNotFoundError):
                test_results.append("❌ aplayコマンドが見つかりません")
            
            try:
                subprocess.run(["which", "paplay"], check=True, capture_output=True)
                paplay_available = True
                test_results.append("✅ paplayコマンド利用可能")
            except (subprocess.CalledProcessError, FileNotFoundError):
                test_results.append("❌ paplayコマンドが見つかりません")
            
            if not aplay_available and not paplay_available:
                test_results.append("⚠️ 音声再生コマンドが見つかりません。alsa-utilsまたはpulseaudio-utilsをインストールしてください")
                
        elif sys.platform == "win32":
            try:
                import pygame
                test_results.append("✅ pygame利用可能")
            except ImportError:
                test_results.append("⚠️ pygame未インストール。Windowsシステムコマンドを使用します")
            
            test_results.append("✅ Windowsシステム音声再生利用可能")
        
        # 結果表示
        test_message = "\n".join(test_results)
        messagebox.showinfo("音声システム テスト結果", test_message)
        
        # ログにも記録
        self.add_message("system", f"音声システム テスト結果:\n{test_message}\n")

    def save_conversation(self):
        """対話ログの保存（.mdファイル対応版）"""
        content = self.conversation_text.get("1.0", tk.END)
        if not content.strip():
            messagebox.showinfo("情報", "保存する内容がありません")
            return

        try:
            # デフォルトファイル名を.mdに変更
            default_filename = f"ollama_a2a_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            
            filename = filedialog.asksaveasfilename(
                defaultextension=".md",
                filetypes=[
                    ("Markdownファイル", "*.md"),
                    ("テキストファイル", "*.txt"), 
                    ("すべてのファイル", "*.*")
                ],
                initialfile=default_filename,
                title="対話ログを保存"
            )
            
            if filename:
                try:
                    # Markdown形式でフォーマット
                    markdown_content = self.format_as_markdown(content)
                    
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(markdown_content)
                    messagebox.showinfo("成功", f"ファイルを保存しました:\n{filename}")
                    self.status_label.config(text=f"保存完了: {os.path.basename(filename)}")
                except Exception as e:
                    messagebox.showerror("エラー", f"保存に失敗しました:\n{str(e)}")
        except Exception as e:
            messagebox.showerror("エラー", f"ファイルダイアログでエラーが発生しました:\n{str(e)}")

    def format_as_markdown(self, content):
        """テキストをMarkdown形式にフォーマット"""
        lines = content.split('\n')
        markdown_lines = []
        
        # ヘッダー追加
        markdown_lines.append("# Ollama A2A 対話ログ")
        markdown_lines.append(f"生成日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
        markdown_lines.append("")
        
        for line in lines:
            line = line.strip()
            if not line:
                markdown_lines.append("")
                continue
                
            # タイムスタンプを除去して内容を解析
            if "] " in line:
                content_part = line.split("] ", 1)[1] if "] " in line else line
            else:
                content_part = line
            
            # Agent応答をMarkdownの引用形式に
            if content_part.startswith("🤖 Agent 1:"):
                markdown_lines.append("## Agent 1 (分析役)")
                markdown_lines.append(f"> {content_part[12:].strip()}")
                markdown_lines.append("")
            elif content_part.startswith("🤖 Agent 2:"):
                markdown_lines.append("## Agent 2 (評価役)")  
                markdown_lines.append(f"> {content_part[12:].strip()}")
                markdown_lines.append("")
            elif content_part.startswith("=== "):
                markdown_lines.append(f"## {content_part}")
                markdown_lines.append("")
            elif content_part.startswith("--- "):
                markdown_lines.append(f"### {content_part}")
                markdown_lines.append("")
            elif content_part.startswith("❌") or content_part.startswith("⚠️"):
                markdown_lines.append(f"**{content_part}**")
                markdown_lines.append("")
            else:
                markdown_lines.append(content_part)
        
        return '\n'.join(markdown_lines)

    def add_message(self, msg_type, content):
        """メッセージをUI表示"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        self.conversation_text.insert(tk.END, f"[{timestamp}] ", "timestamp")
        self.conversation_text.insert(tk.END, content, msg_type)
        self.conversation_text.see(tk.END)

    def play_bell_sound(self):
        """ベル音を一度だけ再生する（改善版）"""
        if self.sound_played:
            return  # 既に再生済みの場合は何もしない
        
        # 音声ファイルの存在確認
        if not self.bell_sound_path.exists():
            self.add_message("error", f"音声ファイルが見つかりません: {self.bell_sound_path}\n")
            return
        
        # ファイルサイズの確認（破損チェック）
        try:
            if self.bell_sound_path.stat().st_size < 100:
                self.add_message("error", "音声ファイルが破損している可能性があります\n")
                return
        except OSError:
            self.add_message("error", "音声ファイルの読み取りに失敗しました\n")
            return
        
        def play_sound():
            try:
                success = False
                error_message = ""
                
                # macOSの場合 - afplayのみ使用（aplayはLinux用）
                if sys.platform == "darwin":
                    try:
                        result = subprocess.run(
                            ["afplay", str(self.bell_sound_path)], 
                            check=True,
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        success = True
                    except subprocess.CalledProcessError as e:
                        error_message = f"afplayエラー: {e.stderr}"
                        # ファイル形式を確認
                        try:
                            file_result = subprocess.run(
                                ["file", str(self.bell_sound_path)], 
                                capture_output=True, text=True
                            )
                            error_message += f" | ファイル形式: {file_result.stdout.strip()}"
                            error_message += " | 🔧 fix_bell_macos.pyで修復してください"
                        except:
                            pass
                    except FileNotFoundError:
                        error_message = "afplayコマンドが見つかりません（macOS標準コマンドのはず）"
                    except subprocess.TimeoutExpired:
                        # タイムアウトでも再生は開始されている可能性
                        success = True
                
                # Linuxの場合
                elif sys.platform.startswith("linux"):
                    # aplayを最初に試行
                    try:
                        result = subprocess.run(
                            ["aplay", str(self.bell_sound_path)], 
                            check=True,
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        success = True
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        # aplayが失敗した場合はpaplayを試行
                        try:
                            result = subprocess.run(
                                ["paplay", str(self.bell_sound_path)], 
                                check=True,
                                capture_output=True,
                                text=True,
                                timeout=10
                            )
                            success = True
                        except subprocess.CalledProcessError as e:
                            error_message = f"paplayエラー: {e.stderr}"
                        except FileNotFoundError:
                            error_message = "aplayもpaplayも見つかりません"
                        except subprocess.TimeoutExpired:
                            error_message = "音声再生がタイムアウトしました"
                
                # Windowsの場合
                elif sys.platform == "win32":
                    # pygameを最初に試行
                    try:
                        import pygame
                        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=1024)
                        pygame.mixer.music.load(str(self.bell_sound_path))
                        pygame.mixer.music.play()
                        
                        # 再生終了まで待機（最大10秒）
                        timeout = 10
                        start_time = time.time()
                        while pygame.mixer.music.get_busy() and (time.time() - start_time) < timeout:
                            time.sleep(0.1)
                        
                        pygame.mixer.quit()
                        success = True
                        
                    except ImportError:
                        # pygameがない場合はWindowsシステムコマンドを使用
                        try:
                            os.system(f'powershell -c "(New-Object Media.SoundPlayer \\"{self.bell_sound_path}\\").PlaySync()"')
                            success = True
                        except Exception as e:
                            error_message = f"Windows音声再生エラー: {str(e)}"
                    except Exception as e:
                        error_message = f"pygame音声再生エラー: {str(e)}"
                
                else:
                    error_message = f"サポートされていないOS: {sys.platform}"
                
                # 結果の処理
                if success:
                    self.sound_played = True
                    self.message_queue.put(("system", "🔔 対話終了のお知らせ音を再生しました\n"))
                else:
                    self.message_queue.put(("error", f"音声再生エラー: {error_message}\n"))
                    self.message_queue.put(("system", "💡 fix_bell.pyで音声ファイルを修復してください\n"))
                    
            except Exception as e:
                self.message_queue.put(("error", f"予期しない音声再生エラー: {str(e)}\n"))
        
        # バックグラウンドで音声再生
        threading.Thread(target=play_sound, daemon=True).start()

    def check_queue(self):
        """メッセージキューの確認（改善版）"""
        try:
            while True:
                msg_type, content = self.message_queue.get_nowait()
                
                if msg_type == "status_ok":
                    self.status_label.config(text=content)
                elif msg_type == "status_error":
                    self.status_label.config(text=content)
                elif msg_type == "models":
                    self.available_models = content
                    self.update_model_combos(content)
                elif msg_type == "model_validation":
                    self.validate_models(content)
                elif msg_type == "finished":
                    self.stop_conversation()
                    # 対話終了時にベル音を再生
                    self.play_bell_sound()
                elif msg_type == "error":
                    self.add_message("error", f"❌ {content}\n")
                elif msg_type == "progress":
                    self.status_label.config(text=content)
                else:
                    self.add_message(msg_type, content)
                    
        except queue.Empty:
            pass
        
        # 100ms後に再チェック
        self.root.after(100, self.check_queue)


def main():
    """アプリケーションのエントリーポイント"""
    root = tk.Tk()
    app = OllamaA2AApp(root)
    
    # macOSでの終了処理
    def on_closing():
        if app.is_running:
            if messagebox.askokcancel("終了確認", "対話が実行中です。終了しますか？"):
                app.stop_conversation()
                time.sleep(0.5)  # 停止処理の完了を待つ
                root.destroy()
        else:
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # アイコン設定（macOS用）
    if sys.platform == "darwin":
        try:
            root.iconbitmap("")
        except:
            pass
    
    root.mainloop()


if __name__ == "__main__":
    main()
