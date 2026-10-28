# BrainStorm Studio

本地 AI 咨询工作台。你写下目标，本机上的多个模型会按流程澄清需求、检索公开资料、讨论方案，并给出可以执行的交付。推理只连接本机或局域网里的 [Ollama](https://ollama.com)，不调用云端 AI，也不需要 AI API Key。

界面可以在中文和英文之间切换。页头的 **中文 / EN** 会切换按钮、说明和团队回复语言。你亲手改过的步骤说明会保留。

A local AI consultancy. You write a goal, and models on your own machine clarify it, search public sources, discuss options, and deliver something you can act on. Inference talks only to [Ollama](https://ollama.com) on this computer or your LAN. There is no cloud AI call and no AI API key.

The page has Chinese and English. **中文 / EN** in the header switches the interface and the language the team writes in. Step instructions you edited yourself stay as you wrote them.

## 准备 / Requirements

- Python 3.11 或更新版本
- Node.js 20 或更新版本
- 已安装并可以运行的 Ollama，以及至少一个本地模型。建议准备 `qwen3.5:9b`，讨论时再加一个不同系列的模型，例如 `llama3.1:8b`

```powershell
ollama pull qwen3.5:9b
```

## 安装 / Install

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
cd frontend
npm install
cd ..
```

macOS 或 Linux 把 Python 换成 `.venv/bin/python`。Python 依赖都在 `requirements.txt`。前端依赖在 `frontend/package.json`，由 `npm install` 安装。

On macOS or Linux, use `.venv/bin/python` instead. Python packages are listed in `requirements.txt`. Frontend packages live in `frontend/package.json` and are installed with `npm install`.

## 启动 / Run

保持 Ollama 运行。

**Windows PowerShell**，构建前端并由后端在 8000 端口提供页面：

```powershell
.\start.ps1
```

浏览器打开 http://127.0.0.1:8000 。第一次运行会构建前端。Ctrl+C 停止。

**Git Bash / macOS / Linux**，同时启动后端和带热更新的前端：

```bash
bash start.sh
```

终端会打印前端地址，默认 http://127.0.0.1:5173 。脚本会避开已被占用的端口。Ctrl+C 会关掉这次启动的两个服务。

也可以分开启动。先在项目根目录运行后端：

```powershell
.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

再开一个终端：

```powershell
cd frontend
npm run dev
```

开发地址是 http://127.0.0.1:5173 ，`/api` 会转发到 8000 端口。

Ollama 默认地址是 `http://127.0.0.1:11434`。如果服务在别的地址，设置环境变量 `OLLAMA_URL`。局域网里的另一台 Ollama 可以在页面里用“接入其他 AI”添加，例如 `http://192.168.1.10:11434`。

## 怎么用 / Use

1. 在沟通区写下目标，点击“开始咨询”。
2. 软件自动安排用户画像、团队讨论、成果交付和模拟反馈。只有会改变方向的条件才会停下来问你。
3. 需要时在流程图里改步骤说明、成员和联网权限。自动模式会补齐空缺成员，并保留你改过的说明。
4. 完成后可以下载最终建议，或写下修改意见再跑一版。
5. “历史项目”可以打开、删除一条，或全部清理。删除只影响这个浏览器里的归档，当前打开的任务会留下。

模拟客户由本地模型扮演，用来挑方案的问题。它不是访谈，也不能证明有人会购买。联网检索只发生在你授权的步骤，搜索关键词会发给外部搜索引擎。来源是搜索摘要，不代表已经读完并核实网页全文。

1. Write the goal and choose Start.
2. The app lines up personas, discussion, delivery, and simulated feedback. It stops to ask only when a missing condition would change the direction.
3. Edit step instructions, members, and web permission on the flow when you need to. Automatic mode fills empty seats and keeps instructions you already changed.
4. Download the final advice, or write what to change and run another version.
5. History can open one archive, delete one, or clear all. Deleting removes a browser archive. The task that is open stays.

Simulated customers are local models looking for problems in a plan. They are not interviews and they do not prove anyone will pay. Web search runs only on steps you authorize, and the keywords go to an external search engine. A source is a search snippet, not a fully read and verified page.

右上角 **中文 / EN** 会记住你的选择。浏览器语言不是中文时，第一次打开默认是英文。正在运行的任务不会改写已经提交的步骤；下一次开始会使用当前语言。

**中文 / EN** remembers the choice. A browser that is not set to Chinese opens in English the first time. A run that is already going keeps the steps it started with. The next run uses the language selected now.

## 数据放在哪里 / Where data lives

任务、对话和归档保存在当前浏览器的 localStorage，最近 8 个有内容的项目会留下来。后端的运行状态在内存里，重启服务后不能接着跑同一次流程，浏览器里已经收到的结果还在。服务只绑定本机地址，没有账号系统。

Projects, conversation, and archives are stored in this browser’s localStorage. The last 8 projects with content are kept. A run’s live state is in memory, so restarting the server cannot resume that run. Results already shown in the browser remain. The server binds to this computer only and has no accounts.

## 检查 / Tests

```powershell
.\.venv\Scripts\python -m unittest discover -s tests
cd frontend
node --test tests/*.test.js
npm run build
```

测试使用模拟的模型和搜索，不需要先下载模型。

The tests use stand-in models and search. You do not need to download a model first.

## 目录 / Layout

- `backend/`：FastAPI 服务和咨询流程
- `frontend/`：React + Vite 页面
- `requirements.txt`：Python 依赖
- `frontend/package.json`：前端依赖
- `start.ps1`：Windows 下一键启动
- `start.sh`：Git Bash、macOS、Linux 启动
