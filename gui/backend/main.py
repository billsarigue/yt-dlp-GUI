from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pathlib import Path
import asyncio, json, re, shutil, uuid, os

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Estado global ──────────────────────────────────────────────────────────────
queue: list[dict] = []
queue_lock = asyncio.Lock()
sse_subscribers: list[asyncio.Queue] = []

AUDIO_FORMATS = {"m4a", "mp3", "opus", "wav"}

# ── Helpers ────────────────────────────────────────────────────────────────────
def find_ytdlp() -> str:
    found = shutil.which("yt-dlp")
    if found:
        return found
    for candidate in [
        Path(os.environ.get("APPDATA", "")) / "Python" / "Scripts" / "yt-dlp.exe",
        Path.home() / ".local" / "bin" / "yt-dlp",
    ]:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError("yt-dlp não encontrado no PATH")

def extract_video_id(url: str) -> str:
    m = re.search(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})', url)
    return m.group(1) if m else ""

def build_format_arg(fmt: str, quality: str) -> str:
    if fmt in AUDIO_FORMATS:
        return "bestaudio/best"
    if quality == "Melhor":
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
    q = quality.replace("p", "")
    return f"bestvideo[ext=mp4][height<={q}]+bestaudio[ext=m4a]/bestvideo[height<={q}]+bestaudio/best"

def build_output_template(output_dir: str) -> str:
    base = output_dir if output_dir else str(Path.home() / "Downloads")
    return os.path.join(base, "%(title)s.%(ext)s")

def build_cmd(ytdlp: str, fmt: str, fmt_arg: str, out_tmpl: str, url: str) -> list[str]:
    cmd = [ytdlp, "--newline", "--progress", "-f", fmt_arg, "-o", out_tmpl]
    if fmt not in AUDIO_FORMATS:
        cmd += ["--merge-output-format", fmt]
    if fmt in {"mp3", "wav", "opus"}:
        cmd += ["--extract-audio", "--audio-format", fmt]
    elif fmt == "m4a":
        cmd += ["--extract-audio", "--audio-format", "m4a"]
    cmd.append(url)
    return cmd

async def get_video_metadata(ytdlp: str, url: str) -> tuple[str, str]:
    proc = await asyncio.create_subprocess_exec(
        ytdlp, "--get-title", "--get-duration", url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    lines = out.decode("utf-8", errors="replace").strip().splitlines()
    title = lines[0] if lines else ""
    duration = lines[1] if len(lines) > 1 else ""
    return title, duration

async def update_item(item_id: str, **fields) -> None:
    async with queue_lock:
        item = next((i for i in queue if i["id"] == item_id), None)
        if item:
            item.update(fields)
    await broadcast()

# ── SSE ────────────────────────────────────────────────────────────────────────
async def broadcast() -> None:
    data = "data: " + json.dumps(queue) + "\n\n"
    for q in sse_subscribers:
        await q.put(data)

@app.get("/api/queue/stream")
async def queue_stream():
    client_q: asyncio.Queue = asyncio.Queue()
    sse_subscribers.append(client_q)

    async def event_generator():
        try:
            yield "data: " + json.dumps(queue) + "\n\n"
            while True:
                yield await client_q.get()
        finally:
            sse_subscribers.remove(client_q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ── Modelos ────────────────────────────────────────────────────────────────────
class DownloadRequest(BaseModel):
    url: str
    format: str = "mp4"
    quality: str = "1080p"
    output_dir: str = ""

# ── Endpoints ──────────────────────────────────────────────────────────────────
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

@app.delete("/api/queue/{item_id}")
async def remove_item(item_id: str):
    async with queue_lock:
        global queue
        queue = [i for i in queue if i["id"] != item_id]
    await broadcast()
    return {"ok": True}

@app.get("/api/debug")
async def debug():
    return {
        "yt_dlp_path": shutil.which("yt-dlp"),
        "PATH": os.environ.get("PATH", ""),
        "cwd": os.getcwd(),
    }

# ── Worker de download ─────────────────────────────────────────────────────────
async def run_download(item_id: str, req: DownloadRequest) -> None:
    try:
        ytdlp = find_ytdlp()
        fmt_arg = build_format_arg(req.format, req.quality)
        out_tmpl = build_output_template(req.output_dir)
        cmd = build_cmd(ytdlp, req.format, fmt_arg, out_tmpl, req.url)

        await update_item(item_id, status="downloading")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        pct, speed, size = 0.0, "", ""
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            print(f"[yt-dlp] {line}")

            m = re.search(r'\[download\]\s+([\d.]+)%(?:.*?of\s+([\d.]+\s*\w+B))?(?:.*?at\s+([\d.]+\s*\w+/s))?', line)
            if m:
                pct = float(m.group(1))
                size = m.group(2) or size
                speed = m.group(3) or speed
                await update_item(item_id, progress=round(pct, 1), speed=speed, size=size)

        await proc.wait()

        title, duration = await get_video_metadata(ytdlp, req.url)
        status = "done" if proc.returncode == 0 else "error"
        await update_item(
            item_id,
            title=title,
            duration=duration,
            status=status,
            progress=100 if status == "done" else round(pct, 1),
            speed="",
        )

    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        await update_item(item_id, status="error", title=str(e), speed="")

# ── Entrypoint ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn, socket

    def get_free_port(preferred: int) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", preferred))
                return preferred
            except OSError:
                s.bind(("127.0.0.1", 0))
                return s.getsockname()[1]

    port = get_free_port(17432)
    uvicorn.run(app, host="127.0.0.1", port=port)
