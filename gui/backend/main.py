'''Backend para gerenciar downloads usando yt-dlp e expor uma API REST para o frontend.'''
import asyncio
import json
import os
import re
import shutil
import sys
import uuid
import subprocess
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Windows Job Object: garante que todos os subprocessos morrem com o backend
if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes

    _kernel32 = ctypes.windll.kernel32

    def _assign_job_object():
        job = _kernel32.CreateJobObjectW(None, None)
        if not job:
            return
        # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        info = (ctypes.c_uint32 * 8)()
        info[4] = 0x2000  # LimitFlags
        _kernel32.SetInformationJobObject(job, 9, info, ctypes.sizeof(info))
        _kernel32.AssignProcessToJobObject(job, _kernel32.GetCurrentProcess())

    _assign_job_object()


# Redireciona stdout/stderr para arquivo de log quando rodando como executável
# (PyInstaller com --noconsole seta sys.stdout = None)
if getattr(sys, "frozen", False) and sys.stdout is None:
    log_path = Path(os.getenv("LOCALAPPDATA", "")) / "yt-dlp-GUI" / "backend.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w", encoding="utf-8", buffering=1)
    sys.stdout = log_file
    sys.stderr = log_file

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

queue: list[dict] = []
queue_lock = asyncio.Lock()
sse_subscribers: list[asyncio.Queue] = []

# CREATE_NO_WINDOW garante que subprocessos (yt-dlp, ffmpeg) não abram janela
# e permaneçam no mesmo process group — morrem junto com o backend
if sys.platform == "win32":
    _si = subprocess.STARTUPINFO()
    _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _si.wShowWindow = subprocess.SW_HIDE
    WIN_FLAGS = {
        "startupinfo": _si,
        "creationflags": 0x08000000,  # CREATE_NO_WINDOW (sem CREATE_NEW_PROCESS_GROUP)
    }
else:
    WIN_FLAGS = {}

async def broadcast():
    data = "data: " + json.dumps(queue) + "\n\n"
    for q in sse_subscribers:
        await q.put(data)

class DownloadRequest(BaseModel):
    url: str
    format: str = "mp4"
    quality: str = "1080p"
    output_dir: str = ""

def find_ytdlp() -> str:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates = [
            exe_dir / "yt-dlp.exe",
            exe_dir / "yt-dlp",
            exe_dir / "_internal" / "yt-dlp.exe",
            exe_dir / "resources" / "backend" / "yt-dlp.exe",
        ]
    else:
        project_root = Path(__file__).parent
        candidates = [
            project_root / "resources" / "backend" / "yt-dlp.exe",
            project_root / "resources" / "backend" / "yt-dlp",
            Path(shutil.which("yt-dlp") or ""),
        ]

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    raise FileNotFoundError("yt-dlp não encontrado")

@app.get("/api/queue/stream")
async def queue_stream():
    client_q: asyncio.Queue = asyncio.Queue()
    sse_subscribers.append(client_q)

    async def event_generator():
        try:
            yield "data: " + json.dumps(queue) + "\n\n"
            while True:
                data = await client_q.get()
                yield data
        finally:
            sse_subscribers.remove(client_q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

def extract_video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else ""

def build_format_arg(fmt: str, quality: str) -> str:
    audio_fmts = {"m4a", "mp3", "opus", "wav"}
    if fmt in audio_fmts:
        return "bestaudio/best"
    if quality == "Melhor":
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
    q = quality.replace("p", "")
    return f"bestvideo[ext=mp4][height<={q}]+bestaudio[ext=m4a]/bestvideo[height<={q}]+bestaudio/best"

def build_output_template(output_dir: str) -> str:
    base = output_dir if output_dir else str(Path.home() / "Downloads")
    return os.path.join(base, "%(title)s.%(ext)s")

@app.post("/api/download")
async def start_download(req: DownloadRequest):
    item_id = str(uuid.uuid4())[:8]
    item = {
        "id": item_id,
        "url": req.url,
        "video_id": extract_video_id(req.url),
        "title": "",
        "duration": "",
        "size": "",
        "formatId": req.format,
        "quality": req.quality,
        "status": "queued",
        "progress": 0,
        "speed": "",
    }
    async with queue_lock:
        queue.append(item)
        await broadcast()

    task = asyncio.create_task(run_download(item_id, req))
    task.add_done_callback(
        lambda t: print("TASK ERROR:", t.exception()) if t.exception() else None
    )
    return {"id": item_id}

async def run_download(item_id: str, req: DownloadRequest):
    pct = 0.0
    speed = ""
    size = ""
    try:
        ytdlp = find_ytdlp()

        async with queue_lock:
            item = next((i for i in queue if i["id"] == item_id), None)
            if item:
                item["status"] = "downloading"
                await broadcast()

        fmt_arg = build_format_arg(req.format, req.quality)
        out_tmpl = build_output_template(req.output_dir)

        cmd = [
            ytdlp,
            "--newline", "--progress",
            "--no-playlist",
            "-f", fmt_arg,
            "-o", out_tmpl,
        ]
        if req.format not in {"mp3", "m4a", "opus", "wav"}:
            cmd += ["--merge-output-format", req.format]
        if req.format in {"mp3", "wav"}:
            cmd += ["--extract-audio", "--audio-format", req.format]
        elif req.format == "m4a":
            cmd += ["--extract-audio", "--audio-format", "m4a"]
        cmd.append(req.url)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **WIN_FLAGS,
        )

        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            m_prog = re.search(
                r"\[download\]\s+([\d.]+)%\s+of\s+([\d.]+\w+)\s+at\s+([\d.]+\w+/s)",
                line,
            )
            if m_prog:
                pct = float(m_prog.group(1))
                size = m_prog.group(2)
                speed = m_prog.group(3)
                async with queue_lock:
                    item = next((i for i in queue if i["id"] == item_id), None)
                    if item:
                        item["progress"] = round(pct, 1)
                        item["speed"] = speed
                        item["size"] = size
                        await broadcast()

        await proc.wait()

        title_proc = await asyncio.create_subprocess_exec(
            ytdlp, "--get-title", "--get-duration", req.url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            **WIN_FLAGS,
        )
        title_out, _ = await title_proc.communicate()
        title = (
            title_out.decode("utf-8", errors="replace").strip().splitlines()[0]
            if title_out
            else ""
        )

        async with queue_lock:
            item = next((i for i in queue if i["id"] == item_id), None)
            if item:
                item["status"] = "done"
                item["progress"] = 100
                item["title"] = title
                await broadcast()

    except Exception as e:
        print(f"[ERROR] {e}")
        async with queue_lock:
            item = next((i for i in queue if i["id"] == item_id), None)
            if item:
                item["status"] = "error"
                await broadcast()

@app.delete("/api/queue/{item_id}")
async def remove_item(item_id: str):
    async with queue_lock:
        global queue
        queue = [i for i in queue if i["id"] != item_id]
        await broadcast()
    return {"ok": True}

@app.get("/api/debug")
async def debug():
    try:
        ytdlp_path = find_ytdlp()
    except FileNotFoundError:
        ytdlp_path = "nao encontrado"
    return {
        "yt_dlp_path": ytdlp_path,
        "cwd": os.getcwd(),
        "exe_dir": str(Path(sys.executable).parent),
    }

if __name__ == "__main__":
    import uvicorn
    import socket

    def get_free_port(preferred: int) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", preferred))
                return preferred
            except OSError:
                s.bind(("127.0.0.1", 0))
                return s.getsockname()[1]

    port = get_free_port(17432)
    print(f"Backend iniciado na porta {port}.")
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_config=None,
        access_log=False,
    )