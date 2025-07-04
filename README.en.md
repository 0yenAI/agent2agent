# Ollama A2A App

🤖 **Hybrid AI Agent-to-Agent Desktop Application**

Ollama A2A App is a desktop application that enables conversations between multiple AI agents by combining local LLMs via Ollama with Google's Gemini and Anthropic's Claude APIs. The goal is to elicit multifaceted perspectives and deeper insights, which are often difficult to achieve with a single AI, by having two agents—an "Analyst" and a "Reviewer"—discuss a topic.

## ✨ Key Features

- **🔄 Hybrid AI Conversations**: Freely combine local models from Ollama with cloud-based models from the Gemini and Claude APIs for your agents.
- **🖥️ Intuitive GUI**: A simple and lightweight interface built with Python's standard tkinter library.
- **📝 Markdown Export**: Easily save the conversation history in a well-organized Markdown format.
- **⚙️ Flexible Configuration**: Flexibly configure the models for each agent, the number of conversation rounds, and the response timeout directly from the GUI.
- **🌍 Cross-Platform**: Runs on both macOS and Linux.
- **🚀 Easy Setup**: Uses the modern Python package manager `uv` to set up the environment and launch the application with a few simple commands.

## 🛠️ System Requirements

- **OS**: macOS or Linux
- **Python**: 3.12 or later
- **uv**: Must be [installed](https://astral.sh/uv/install.sh).
- **Ollama**: The latest version must be installed and the service running.
  - **Important**: The context size (number of tokens) of Ollama models varies depending on the model used. If the "Timeout (seconds)" setting or the internal `num_ctx` and `num_predict` values exceed the model's maximum token limit, the application may crash or behave unexpectedly. Please check the recommended context size for your Ollama model and set appropriate values.

## 🚀 Setup & Launch

### 1. Prepare Ollama

First, install Ollama from the [official website](https://ollama.com/) and start the service.

```bash
# Start the Ollama service (run in a terminal)
ollama serve
```

Next, download the models you want to use for the conversation.

```bash
# Example: Download a lightweight and a high-performance model
ollama pull llama3:8b
ollama pull gemma:7b
```

### 2. Application Setup and Launch

In the directory where you cloned or downloaded the repository, run the following commands:

```bash
# 1. Create the virtual environment
uv venv

# 2. Install the project (which also installs dependencies)
uv pip install -e .

# 3. Launch the application
uv run ollama_a2a_app/main.py
```

The `uv run` command executes the script directly using the Python interpreter in the virtual environment.

### 3. Configure API Keys (Optional)

If you plan to use Gemini or Claude models, you need to configure your API key(s).

1.  Click the `⚙️ Settings` button in the top-right corner of the application.
2.  Enter your Gemini and/or Claude API key in the dialog that appears and click "Save".
3.  The API key(s) will be securely stored in files named `.gemini_api_key` and/or `.claude_api_key` in the project root.

## 📄 License

This project is licensed under the **Apache License 2.0**.