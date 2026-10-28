# BrainStorm Studio

A local AI consultancy. You write a goal, and models on your own machine clarify it, search public sources, discuss options, and deliver something you can act on. Inference talks only to [Ollama](https://ollama.com) on this computer or your LAN. There is no cloud AI call and no AI API key.

The page has Chinese and English. **中文 / EN** in the header switches the interface and the language the team writes in. Step instructions you edited yourself stay as you wrote them.

## Requirements

- Python 3.11 or newer
- Node.js 20 or newer
- A running Ollama install and at least one local model. `qwen3.5:9b` is a good default. For discussion, add a model from another family, such as `llama3.1:8b`.

```powershell
ollama pull qwen3.5:9b
```

## Install

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
cd frontend
npm install
cd ..
```

On macOS or Linux, use `.venv/bin/python` instead. Python packages are listed in `requirements.txt`. Frontend packages live in `frontend/package.json` and are installed with `npm install`.

## Run

Keep Ollama running.

**Windows PowerShell.** This builds the frontend and serves the page from the backend on port 8000:

```powershell
.\start.ps1
```

Open http://127.0.0.1:8000 . The first run builds the frontend. Press Ctrl+C to stop.

**Git Bash, macOS, or Linux.** This starts the backend and a frontend with hot reload:

```bash
bash start.sh
```

The terminal prints the frontend address. The default is http://127.0.0.1:5173 . The script skips ports that are already in use. Ctrl+C stops both processes started by this script.

You can also start them separately. From the project root:

```powershell
.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm run dev
```

The dev page is http://127.0.0.1:5173 . Requests to `/api` are forwarded to port 8000.

Ollama defaults to `http://127.0.0.1:11434`. Set `OLLAMA_URL` when the service is somewhere else. Another Ollama on your LAN can be added in the page with “Connect another AI”, for example `http://192.168.1.10:11434`.

## Use

1. Write the goal and choose Start.
2. The app lines up personas, discussion, delivery, and simulated feedback. It stops to ask only when a missing condition would change the direction.
3. Edit step instructions, members, and web permission on the flow when you need to. Automatic mode fills empty seats and keeps instructions you already changed.
4. Download the final advice, or write what to change and run another version.
5. History can open one archive, delete one, or clear all. Deleting removes a browser archive. The task that is open stays.

Simulated customers are local models looking for problems in a plan. They are not interviews and they do not prove anyone will pay. Web search runs only on steps you authorize, and the keywords go to an external search engine. A source is a search snippet, not a fully read and verified page.

**中文 / EN** remembers the choice. A browser that is not set to Chinese opens in English the first time. A run that is already going keeps the steps it started with. The next run uses the language selected now.

## Where data lives

Projects, conversation, and archives are stored in this browser’s localStorage. The last 8 projects with content are kept. A run’s live state is in memory, so restarting the server cannot resume that run. Results already shown in the browser remain. The server binds to this computer only and has no accounts.

## Tests

```powershell
.\.venv\Scripts\python -m unittest discover -s tests
cd frontend
node --test tests/*.test.js
npm run build
```

The tests use stand-in models and search. You do not need to download a model first.

## Layout

- `backend/`: FastAPI service and the consultancy flow
- `frontend/`: React + Vite page
- `requirements.txt`: Python dependencies
- `frontend/package.json`: frontend dependencies
- `start.ps1`: one-step start on Windows
- `start.sh`: start on Git Bash, macOS, and Linux

## License

[MIT](LICENSE). Copyright (c) 2026 Mai He.
