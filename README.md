# Torque

A local-first, voice-driven personal assistant for Windows.

Press the hotkey, talk, and Torque listens, understands, acts (open/close apps,
web search, time/date), and answers out loud, while a small orb UI shows what
it is doing.

```
hotkey -> microphone -> Silero VAD -> faster-whisper -> brain -> Piper TTS
                                                         |
                    app commands | web search (Tavily) | local LLM (Ollama) + memory
                                                         |
                                     WebSocket -> React/Three.js orb UI
```

## Requirements

- Windows 10/11 (app launching, hotkey and tray are Windows-specific)
- Python 3.14 and [uv](https://docs.astral.sh/uv/)
- Node.js 20+ (for the UI)
- [Ollama](https://ollama.com) running locally
- A microphone and speakers

## Setup

```powershell
# 1. Python dependencies
uv sync

# 2. UI dependencies
cd torque-ui; npm install; cd ..

# 3. Language model
ollama pull qwen2.5:3b

# 4. Voice (Piper)
uv run python -m piper.download_voices en_US-lessac-medium --download-dir models/piper

# 5. Optional: web search
copy .env.example .env      # then put your Tavily key in .env
```

## Run

```powershell
uv run torque
```

Torque starts the UI, opens it in an app window, and sits in the system tray.
First start is slow while models load.

| Action | How |
| --- | --- |
| Start talking | `Ctrl+Space` (configurable) |
| Cancel / stop talking | `Ctrl+Space` again, or say "bye" |
| Ends on its own | after `listen_timeout` seconds of silence |

Try: "open chrome", "open spotify and then open discord", "close discord",
"what time is it", "what's the weather in Toronto", "my laptop has 32 GB of RAM"
(remembered), then "how much RAM does my laptop have".

## Configuration

`config/settings.json` (created on first run; missing keys use defaults).

| Key | Default | Meaning |
| --- | --- | --- |
| `hotkey` | `ctrl+space` | Global hotkey |
| `hotkey_suppress` | `false` | Block the hotkey from reaching the focused app |
| `listen_timeout` | `10.0` | Seconds of silence before the conversation ends |
| `voice_enabled` | `true` | Speak replies |
| `llm_model` | `qwen2.5:3b` | Ollama model |
| `llm_num_predict` | `200` | Max tokens per reply |
| `whisper_model` | `base` | faster-whisper model size |
| `piper_voice` | `en_US-lessac-medium` | Voice file name in `models/piper/` |
| `ws_host` / `ws_port` | `localhost` / `8765` | WebSocket address |
| `ui_autostart` | `true` | Start the React dev server |
| `ui_window` | `true` | Open the UI in an Edge/Chrome app window |
| `tray_enabled` | `true` | Show the tray icon |

## Layout

```
src/torque/
  main.py              entry point
  paths.py             every filesystem path (anchored to the repo, not the CWD)
  core/                runtime, assistant controller (conversation loop), conversation manager
  system/              services (config, logging, db, hotkey), command router, app matching/launching
  ai/                  brain (routing), Ollama client, system prompt, context builder
  conversation/        speech analysis, conversation policy, stop phrases
  audio/               microphone + VAD, utterance state machine, Whisper, Piper TTS
  memory/              SQLite memory store, extraction, retrieval
  web/                 search router (when to search) and Tavily client
  websocket/           local WebSocket hub (Origin-checked)
  ui/                  UI launcher, tray
torque-ui/             React + Three.js orb
tests/                 pytest suite
```

### How a request flows (`TorqueBrain.process`)

1. Time/date questions are answered locally.
2. App commands (`open`, `launch`, `close`; `start`, `run`, `quit`, `exit` only
   when they name a real app, so "quit smoking tips" is just a sentence).
3. Web search for news, weather, scores, prices, "latest ..." questions.
4. Otherwise the local LLM, with relevant memories added to the prompt.

### WebSocket protocol

Torque -> UI: `{"state": "idle|loading|listening|thinking|searching|speaking|error", "message": "..."}`
(the latest state is replayed to new clients).
UI -> Torque: `{"type": "cancel"}` or `{"type": "text", "text": "open chrome"}`.
Only browser pages served from the UI origin (and non-browser clients) may connect.

## Tests

```powershell
uv run pytest
```

The suite covers routing, speech analysis, app matching, memory, the
microphone state machine, streaming TTS, the conversation loop and the
WebSocket server. It does not need audio hardware, Ollama or an API key.

## Notes

- `data/` (memory database), `logs/`, `models/` and `.env` are git-ignored.
- Transcripts of what you say are written to `logs/torque.log`.
- `close` asks apps to close politely (like clicking X) and refuses to touch
  Explorer and other system processes.
