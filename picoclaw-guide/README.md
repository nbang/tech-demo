# PicoClaw Setup Guide: OpenRouter API & Telegram Bot

This guideline explains how to set up and run PicoClaw (<https://docs.picoclaw.io/>) using OpenRouter (an OpenAI-compatible API) with the `gpt-oss` 120b model, combined with a Telegram bot.

## Prerequisites

1. **OpenRouter API Key**: You need an API key from OpenRouter to access the `gpt-oss-120b` model.
2. **Telegram Bot Token**:
   - Open Telegram and search for **[@BotFather](https://t.me/BotFather)**.
   - Start a chat with BotFather and send the command `/newbot`.
   - Follow the on-screen instructions to set a name and a unique username (must end in `bot`) for your bot.
   - Once completed, BotFather will provide you with an **HTTP API Token** (e.g., `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`). Copy and save this token.

## 1. Installing PicoClaw

You must have PicoClaw installed on your machine.

### Installing via Winget (Windows)

If you want to install PicoClaw to a custom location using Windows Package Manager (`winget`), you can pass the `--location` flag. Open your terminal and run:

```powershell
winget install sipeed.picoclaw --location "D:\app\picoclaw"
```

*Note: You may need to restart your terminal or manually add `D:\app\picoclaw` to your system's PATH variable to run `picoclaw` from anywhere.*

### Alternative Installation

PicoClaw is also distributed as a single self-contained binary. You can download the appropriate binary for your system (Windows, Linux, macOS) from the [PicoClaw Releases](https://github.com/sipeed/picoclaw/releases) page.

### Initialization

Once installed or downloaded, you can initialize your PicoClaw workspace by running:

```powershell
picoclaw onboard
```

This will create your default workspace at `~/.picoclaw/`.

## 2. Configuration File

PicoClaw relies on a central configuration file located at `~/.picoclaw/config.json`.

A sample configuration file designed for OpenRouter and Telegram is provided in this folder: `picoclaw-guide/config.json`. It is pre-configured to use the `gpt-oss-120b` model via OpenRouter's OpenAI-compatible endpoint.

To set up your configuration:

1. Open `config.json` in this folder.
2. Replace `YOUR_OPENROUTER_API_KEY` with your actual OpenRouter API key.
3. Replace `YOUR_TELEGRAM_BOT_TOKEN` with your Telegram bot token.
4. Copy the modified file to your PicoClaw configuration directory:

```powershell
# Copy the config.json file
Copy-Item .\config.json -Destination $HOME\.picoclaw\config.json
```

## 3. Environment Variables (Optional)

PicoClaw also supports setting configuration values via environment variables. If you prefer not to hardcode your API keys in the `config.json`, you can define them in your environment.

A sample `.env` file is provided in this directory. If you run PicoClaw from a terminal where these are exported, you can structure your startup script to inject them:

```powershell
# Set your OpenRouter API key
$env:PICOCLAW_MODEL_LIST_0_API_KEY="your_openrouter_api_key_here"

# Set your Telegram Bot Token
$env:PICOCLAW_CHANNELS_TELEGRAM_BOT_TOKEN="your_telegram_bot_token_here"
```

*Note: For simplicity, modifying the `~/.picoclaw/config.json` directly as shown in step 2 is usually the fastest method.*

## 4. Running PicoClaw

Once the configuration is in place, you can start PicoClaw.

### Starting the Agent (with Telegram & API)

Run the following command in your terminal to bring your agent online and connect it to Telegram:

```powershell
picoclaw agent
```

PicoClaw will connect to OpenRouter to utilize the `gpt-oss-120b` model and initialize the Telegram channel adapter using your bot token.

### Interacting via CLI

If you want to send a quick one-shot message to test the OpenRouter connection without Discord:

```powershell
picoclaw agent -m "Hello, are you using the 120b model?"
```

That's it! Your ultra-efficient AI assistant is ready.
