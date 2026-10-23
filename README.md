# Torque

A local-first, voice-driven personal assistant for Windows.

Say **"Hey Torque"** (or press the hotkey) and a small card slides up over
whatever you are doing. Torque listens, understands, acts (open/close apps, web
search, time/date) and answers out loud, then slides away.

```
"Hey Torque" / hotkey -> mic -> Silero VAD (onnx) -> faster-whisper -> brain -> Piper TTS
                                                                        |      (speaks while the
                          app commands | web search (Tavily) |          |       reply is still
                          local LLM (Ollama, streamed) + memory    -----+       being written)
                                                                        |
                                 WebSocket -> React overlay (Electron, transparent, always on top)
```

## Requirements

- Windows 10/11 (app launching, hotkey and tray are Windows-specific)
- Python 3.14 and [uv](https://docs.astral.sh/uv/)
- Node.js 20+ (for the overlay UI)
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

Torque builds the UI on first run (`npm run build`, automatic), starts the
overlay and sits in the system tray. First start is slower: it downloads the
Whisper `base.en` model (~150 MB) and loads everything in parallel.

| Action | How |
| --- | --- |
| Start talking | say **"Hey Torque"**, or `Ctrl+Space` (configurable), or tray -> Talk to Torque |
| One breath | "Hey Torque, open Chrome" (no chime, runs straight away) |
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
| `wake_word_enabled` | `true` | Listen for "Hey Torque" (needs the always-on mic, see Notes) |
| `chime_enabled` | `true` | Soft chime when Torque starts listening |
| `listen_timeout` | `10.0` | Seconds of silence before the first turn is abandoned |
| `followup_timeout` | `7.0` | Seconds to wait for a follow-up before the conversation ends |
| `end_of_speech_silence` | `0.9` | Pause that ends a long sentence (lower = snappier) |
| `end_of_speech_silence_short` | `0.5` | Pause that ends a short command |
| `voice_enabled` | `true` | Speak replies |
| `llm_model` | `qwen2.5:3b` | Ollama model |
| `llm_num_predict` | `200` | Max tokens per reply |
| `whisper_model` | `base.en` | faster-whisper model (`small.en` is more accurate, slower) |
| `whisper_device` | `cpu` | `cpu`, `cuda` or `auto` (falls back to CPU on error) |
| `llm_num_ctx` | `2048` | LLM context window (smaller = faster) |
| `web_search_depth` | `basic` | Tavily depth; `advanced` is slower |
| `piper_voice` | `en_US-lessac-medium` | Voice file name in `models/piper/` |
| `ws_host` / `ws_port` | `localhost` / `8765` | WebSocket address |
| `ui_mode` | `overlay` | `overlay` (Electron card), `window` (Edge/Chrome app window) or `none` |
| `ui_port` | `5174` | Local port the built UI is served on (127.0.0.1 only) |
| `overlay_position` | `bottom` | `bottom`, `top` or `center` |
| `tray_enabled` | `true` | Show the tray icon |

## Layout

```
src/torque/
  main.py              entry point
  paths.py             every filesystem path (anchored to the repo, not the CWD)
  core/                runtime, assistant controller (conversation loop), conversation manager
  system/              services (config, logging, db, hotkey), command router, app matching/launching
  ai/                  brain (routing), Ollama client, system prompt, context builder
  conversation/        wake word, speech analysis, conversation policy, stop phrases
  audio/               mic stream, VAD (onnx), utterance state machine, Whisper, Piper TTS, chime
  memory/              SQLite memory store, extraction, retrieval
  web/                 search router (when to search) and Tavily client
  websocket/           local WebSocket hub (Origin-checked)
  ui/                  UI launcher, static server, tray
torque-ui/             React + Three.js overlay; electron/ holds the transparent window
tests/                 pytest suite
```

### How a request flows (`TorqueBrain.process_stream`)

1. Time/date questions are answered locally.
2. App commands (`open`, `launch`, `close`; `start`, `run`, `quit`, `exit` only
   when they name a real app, so "quit smoking tips" is just a sentence).
3. Web search for news, weather, scores, prices, "latest ..." questions.
4. Otherwise the local LLM, with relevant memories added to the prompt.

### WebSocket protocol

Torque -> UI: `{"state": "idle|loading|listening|thinking|searching|speaking|error", "message": "...", "heard": "..."}`
(`heard` is what Torque understood; the latest state is replayed to new clients),
and `{"level": 0.0-1.0}` microphone loudness while listening (not replayed).
UI -> Torque: `{"type": "cancel"}`, `{"type": "activate"}` or `{"type": "text", "text": "open chrome"}`.
Only browser pages served from the UI origin (and non-browser clients) may connect.

## Tests

```powershell
uv run pytest
```

The suite covers routing, speech analysis, app matching, memory, the
wake word, VAD and microphone state machine (against a real speech sample),
streaming LLM/TTS, the conversation loop, the UI server and the WebSocket server.
`npm test` in `torque-ui` checks the overlay's window placement. It does not need audio hardware, Ollama or an API key.

## Notes

- `data/` (memory database), `logs/`, `models/` and `.env` are git-ignored.
- **Microphone:** with the wake word on, the mic stays open. Audio never leaves
  your PC (Whisper runs locally) and speech that is not addressed to Torque is
  discarded without being logged. Set `wake_word_enabled` to `false` to use only
  the hotkey. Windows will show its "microphone in use" indicator while it is on.
- What you say *to* Torque (after the wake word) is written to `logs/torque.log`.
- `close` asks apps to close politely (like clicking X) and refuses to touch
  Explorer and other system processes.
