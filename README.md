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

PC control (Windows): "volume up / down", "set the volume to 30", "mute",
"pause", "next song", "previous song", "take a screenshot" (saved to
`Pictures/Torque`), "lock my computer", "show desktop", "switch window",
"brightness up", "set brightness to 40" (laptop screens). Hard-to-undo actions
(shut down, restart, sleep) ask first and only run after you say "yes".

**Security copilot** (read-only, about this PC): "what ports are open", "what's
using my network", "what's using my CPU / memory", "any suspicious programs",
"who's on my Wi-Fi". Suspicious-program checks are heuristics (programs running
from Temp/Downloads, system names outside the Windows folder): a lead to check,
not a malware scan, and Torque says so.

**Screen awareness:** "what's this error?", "explain this", "summarize this
page", "what's on my screen". Torque screenshots, reads the text with local OCR
and the local model explains it. Needs the OCR add-on once: `uv sync --extra screen`.
Screen text is never logged or sent anywhere.

**File tasks (local agent):** "unzip my latest download and copy it to D: in a
folder called Projects", "find my resume file", "make a folder called School on
the desktop". Runs a small local model (`ollama pull qwen3:4b`, one-time) that
calls file tools and reads each result, e.g. if the folder doesn't exist it
makes it first. It never deletes or overwrites, won't touch system folders, and
stops if it gets stuck. Weaker than a big model: keep requests explicit.

**Phone access** (off by default, `phone_enabled`): open Torque from your phone's
browser. Start Torque, copy the link it prints (the secret token is in the
`#fragment`), open it on the phone. Safety: a token is required, repeated wrong
tokens lock the address out, power actions (shut down, restart, sleep) are
refused from the phone, and replies are not spoken on the PC. The connection is
plain HTTP, so on networks you don't trust use [Tailscale](https://tailscale.com)
and set `phone_host` to your Tailscale address. Delete `data/phone_token.txt` to
rotate the token. Typing works everywhere; use your phone keyboard's mic to talk.

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
| `pc_control_enabled` | `true` | Volume/media/window/screenshot/power skills |
| `security_skills_enabled` | `true` | Ports / network / process questions |
| `screen_enabled` | `true` | "What's this error?" (needs `uv sync --extra screen`) |
| `agent_enabled` | `true` | Local tool-calling agent for file tasks |
| `agent_model` / `agent_max_steps` | `qwen3:4b` / `8` | Agent model and step limit |
| `phone_enabled` | `false` | Phone access (see above) |
| `phone_host` / `phone_port` | `0.0.0.0` / `8766` | Where the phone page listens |
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
  skills/              PC-control + security skills, permission tiers (safe / confirm), Windows backend
  screen/              screenshot -> OCR -> local LLM
  agent/               tool-calling loop, file tools, task routing
  phone/               phone web page + token-authenticated WebSocket
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
2. PC-control and security skills (`skills/`); a pending "are you sure?" gets the next sentence first.
3. Screen questions (`screen/`).
4. File tasks go to the agent (`agent/`).
5. App commands (`open`, `launch`, `close`; `start`, `run`, `quit`, `exit` only
   when they name a real app, so "quit smoking tips" is just a sentence).
6. Web search for news, weather, scores, prices, "latest ..." questions.
7. Otherwise the local LLM, with relevant memories added to the prompt.

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
