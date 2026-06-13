# backend/downloader.py
import asyncio, subprocess, sys, re, os
from pathlib import Path

FORMAT_OPTS = {
    # video
    "mp4":  ["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]", "--merge-output-format", "mp4"],
    "webm": ["-f", "bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=webm]", "--merge-output-format", "webm"],
    "mkv":  ["-f", "bestvideo+bestaudio", "--merge-output-format", "mkv"],
    # audio
    "m4a":  ["-f", "bestaudio[ext=m4a]/bestaudio", "--extract-audio", "--audio-format", "m4a"],
    "mp3":  ["-f", "bestaudio", "--extract-audio", "--audio-format", "mp3"],
    "opus": ["-f", "bestaudio[ext=opus]/bestaudio", "--extract-audio", "--audio-format", "opus"],
    "wav":  ["-f", "bestaudio", "--extract-audio", "--audio-format", "wav"],
}

QUALITY_MAP = {
    "2160p": "3840", "1440p": "2560", "1080p": "1920",
    "720p": "1280", "480p": "854",
    "320 kbps": "320", "256 kbps": "256",
    "192 kbps": "192", "128 kbps": "128",
}

class YtdlpDownloader:
    def __init__(self, queue):
        self.queue = queue

    def _build_cmd(self, req, output_dir: str) -> list[str]:
        fmt_opts = FORMAT_OPTS.get(req.format_id, FORMAT_OPTS["mp4"])
        out = Path(output_dir or Path.home() / "Downloads")
        out.mkdir(parents=True, exist_ok=True)
        
        cmd = ["yt-dlp", "--newline", "--progress",
               "-o", str(out / "%(title)s.%(ext)s"),
               *fmt_opts]

        # Restrição de qualidade para vídeo
        if req.quality != "Melhor" and req.format_id in ("mp4", "webm", "mkv"):
            width = QUALITY_MAP.get(req.quality)
            if width:
                cmd += ["-f", f"bestvideo[width<={width}]+bestaudio/best[width<={width}]",
                        "--merge-output-format", req.format_id]

        # Bitrate para áudio
        if req.quality != "Melhor" and req.format_id in ("mp3", "m4a", "opus", "wav"):
            kbps = QUALITY_MAP.get(req.quality, "192").replace(" kbps", "")
            cmd += ["--audio-quality", kbps + "K"]

        cmd.append(req.url)
        return cmd

    async def process(self, item_id: str, req):
        await self.queue.update(item_id, status="downloading", progress=0)
        try:
            cmd = self._build_cmd(req, req.output_dir)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            async for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace")
                # Parseando o progresso do yt-dlp: "[download]  47.3% of ..."
                m = re.search(r'\[download\]\s+([\d.]+)%', line)
                if m:
                    pct = float(m.group(1))
                    speed_m = re.search(r'at\s+([\d.]+\s*\w+/s)', line)
                    speed = speed_m.group(1) if speed_m else ""
                    await self.queue.update(item_id, progress=pct, speed=speed)

            await proc.wait()
            if proc.returncode == 0:
                await self.queue.update(item_id, status="done", progress=100)
            else:
                await self.queue.update(item_id, status="error", progress=0)
        except Exception as e:
            await self.queue.update(item_id, status="error", error=str(e))

    async def fetch_info(self, url: str) -> dict:
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp", "--dump-json", "--no-download", url,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, _ = await proc.communicate()
        if proc.returncode == 0:
            import json
            data = json.loads(out)
            return {
                "title": data.get("title", ""),
                "thumbnail": data.get("thumbnail", ""),
                "duration": data.get("duration", 0),
                "channel": data.get("uploader", ""),
            }
        return {}
