# OpenFang Setup Guide: Nvidia API & Telegram Chatbot

This guideline explains how to set up and run OpenFang (<https://www.openfang.sh/>) using the Nvidia API combined with a Telegram chatbot.

## Prerequisites

1. **Nvidia API**: You need the associated API key.
2. **Telegram Bot Token**: Create a bot using BotFather on Telegram and copy its token.

## 1. Installing OpenFang

The default installation in Windows uses Windows Package Manager (`winget`), which does not require Rust to be installed.

### Standard Installation (`winget`)

To install OpenFang globally onto your system, open your terminal and run:

```powershell
winget install OpenFang
```

### Installing to a Specific Directory (`winget`)

If you want to install OpenFang to a custom location, you can pass the `--location` flag:

```powershell
winget install OpenFang --location "D:\app\openfang"
```

*Note: You may need to restart your terminal or manually add `D:\app\openfang` to your system's PATH variable to run `openfang` from anywhere.*

### Alternative Installation (`cargo`)

If you already have a Rust development environment, you can use `cargo` as an alternative method:

```powershell
cargo install openfang
```

## 2. Completely Removing OpenFang

If you want to uninstall and completely remove OpenFang and its configurations from your machine:

1. **Uninstall the application:**
   If you installed via `winget`:

   ```powershell
   winget uninstall OpenFang
   ```

   If you installed via `cargo`:

   ```powershell
   cargo uninstall openfang
   ```

2. **Remove the `.openfang` configurations and databases:**

   ```powershell
   Remove-Item -Recurse -Force $HOME\.openfang
   ```

## 3. Configuration File

OpenFang relies on a central configuration file located at `~/.openfang/config.toml`.

A sample configuration file is provided in this folder: `openfang-demo/config.toml`.

To set up your configuration, copy the local sample file to the OpenFang directory:

```powershell
# Create the .openfang directory if it doesn't exist
New-Item -ItemType Directory -Force -Path $HOME\.openfang

# Copy the config.toml file
Copy-Item .\config.toml -Destination $HOME\.openfang\config.toml
```

*Note: You can open `$HOME\.openfang\config.toml` to provide your own hardcoded values, or rely on environment variables (as configured).*

## 4. Setting Environment Variables

In the sample config, OpenFang expects the API key and Telegram token to be provided via environment variables to keep them secure.

Before running OpenFang, open your terminal (PowerShell) and set the variables:

```powershell
# Set your Nvidia API key (Required)
$env:NVIDIA_API_KEY="your_nvidia_api_key_here"

# Set your Telegram Bot Token (Optional if you only want to use Dashboard/CLI)
$env:TELEGRAM_BOT_TOKEN="your_telegram_bot_token_here"
```

## 5. Running OpenFang

Once the configuration is in place, you can start OpenFang.

### Starting the Daemon (with Telegram & API)

Run the following command in your terminal:

```powershell
openfang start
```

*(If you are building from source, use `cargo run --release -- start`)*

OpenFang will connect to the Nvidia API and initialize the Telegram channel adapter.

### Using the Chat CLI (No Telegram required)

If you prefer to chat with your agent directly from the terminal without setting up a Telegram bot, use the `chat` command:

```powershell
openfang chat
```

This will launch an interactive terminal interface where you can communicate with your configured agent.

### Accessing the Web Dashboard

OpenFang provides a built-in dashboard for monitoring agents, workflows, and configurations. You can launch the UI by running:

```powershell
openfang ui
```

*(Or alternatively, it may be accessible at `http://localhost:4200` when the daemon is running, depending on your setup).*
