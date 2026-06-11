#!/usr/bin/env python3
"""
yt-dlp GUI — interface gráfica que executa a CLI do yt-dlp em subprocessos.

Arquitetura:
  - A GUI (Tkinter, thread principal) jamais bloqueia: cada comando roda em
    subprocess.Popen dentro de uma thread de trabalho (worker).
  - A worker lê stdout/stderr linha a linha e deposita mensagens numa
    queue.Queue; a thread principal drena a fila a cada 100 ms (tk.after),
    técnica canônica para atualização thread-safe de widgets Tkinter.
  - A saída da CLI é interpretada por regex:
      * progresso:  "[download]  45.2% of 10.53MiB at 1.21MiB/s ETA 00:05"
      * destino:    "[download] Destination: ..."
      * mesclagem:  "[Merger] ..." / "[ExtractAudio] ..."
  - Metadados (título, duração, uploader) são obtidos com `yt-dlp -J`
    (--dump-single-json) e decodificados com o módulo json.
  - O cancelamento usa Popen.terminate() (SIGTERM; no Windows, TerminateProcess).

Requisitos: Python 3.10+, yt-dlp acessível (binário no PATH, caminho
explícito, ou o próprio fork via `python -m yt_dlp` a partir da raiz do repo).
ffmpeg é recomendado para mesclagem de fluxos e extração de áudio.

Uso a partir do seu fork (billsarigue/yt-dlp-GUI):
    coloque este arquivo na raiz do repositório e execute
        python yt_dlp_gui.py
    A GUI detectará o pacote yt_dlp local e o usará via `python -m yt_dlp`.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

# --------------------------------------------------------------------------
# Localização do executável da CLI
# --------------------------------------------------------------------------

def detectar_comando_base() -> list[str]:
    """Determina, em ordem de preferência, como invocar a CLI do yt-dlp.

    1. Pacote `yt_dlp` no diretório deste script (o caso do fork clonado):
       invoca `python -m yt_dlp`, garantindo que a GUI use o código do fork.
    2. Binário `yt-dlp` (ou yt-dlp.exe) no PATH.
    3. Fallback: `python -m yt_dlp` (se instalado via pip no mesmo interpretador).
    """
    raiz = Path(__file__).resolve().parent
    if (raiz / "yt_dlp" / "__main__.py").exists():
        return [sys.executable, "-m", "yt_dlp"]
    binario = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if binario:
        return [binario]
    return [sys.executable, "-m", "yt_dlp"]


# --------------------------------------------------------------------------
# Padrões de interpretação da saída da CLI
# --------------------------------------------------------------------------

RE_PROGRESSO = re.compile(
    r"\[download\]\s+(?P<pct>\d{1,3}(?:\.\d+)?)%"
    r"(?:\s+of\s+~?\s*(?P<total>[\d.]+\w+))?"
    r"(?:\s+at\s+(?P<vel>[\d.]+\w+/s|Unknown\s*B/s))?"
    r"(?:\s+ETA\s+(?P<eta>[\d:]+|Unknown))?"
)
RE_DESTINO = re.compile(r"\[download\]\s+Destination:\s+(?P<arquivo>.+)")
RE_JA_BAIXADO = re.compile(r"\[download\]\s+(?P<arquivo>.+) has already been downloaded")
RE_ITEM_PLAYLIST = re.compile(r"\[download\]\s+Downloading item (?P<n>\d+) of (?P<total>\d+)")
RE_POSPROC = re.compile(r"\[(Merger|ExtractAudio|VideoConvertor|VideoRemuxer|EmbedThumbnail|Metadata|FixupM3u8)\]")
RE_ERRO = re.compile(r"^ERROR:\s*(?P<msg>.+)")
RE_AVISO = re.compile(r"^WARNING:\s*(?P<msg>.+)")


@dataclass
class Msg:
    """Mensagem trafegada da worker para a thread da GUI."""
    tipo: str          # 'log' | 'progresso' | 'status' | 'fim' | 'info_json' | 'formatos'
    dado: object = None
    extra: object = None


# --------------------------------------------------------------------------
# Aplicação
# --------------------------------------------------------------------------

class YtDlpGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("yt-dlp GUI")
        self.geometry("860x680")
        self.minsize(760, 560)

        self.cmd_base = detectar_comando_base()
        self.fila: queue.Queue[Msg] = queue.Queue()
        self.processo: subprocess.Popen | None = None
        self.worker: threading.Thread | None = None

        self._montar_interface()
        self._log(f"Comando base detectado: {' '.join(self.cmd_base)}")
        if not shutil.which("ffmpeg"):
            self._log("AVISO: ffmpeg não encontrado no PATH; mesclagem de "
                      "vídeo+áudio e extração de áudio podem falhar.")
        self.after(100, self._drenar_fila)
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)

    # ---------------------------- interface ------------------------------

    def _montar_interface(self) -> None:
        raiz = ttk.Frame(self, padding=10)
        raiz.pack(fill="both", expand=True)

        # --- URL ---
        quadro_url = ttk.LabelFrame(raiz, text="URL", padding=8)
        quadro_url.pack(fill="x")
        self.var_url = tk.StringVar()
        ttk.Entry(quadro_url, textvariable=self.var_url).pack(
            side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(quadro_url, text="Colar",
                   command=self._colar_url).pack(side="left")

        # --- Destino ---
        quadro_dest = ttk.LabelFrame(raiz, text="Pasta de destino", padding=8)
        quadro_dest.pack(fill="x", pady=(8, 0))
        self.var_destino = tk.StringVar(value=str(Path.home() / "Downloads"))
        ttk.Entry(quadro_dest, textvariable=self.var_destino).pack(
            side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(quadro_dest, text="Procurar…",
                   command=self._escolher_pasta).pack(side="left")

        # --- Opções ---
        quadro_op = ttk.LabelFrame(raiz, text="Opções", padding=8)
        quadro_op.pack(fill="x", pady=(8, 0))

        ttk.Label(quadro_op, text="Modo:").grid(row=0, column=0, sticky="w")
        self.var_modo = tk.StringVar(value="video")
        ttk.Radiobutton(quadro_op, text="Vídeo (melhor qualidade)",
                        variable=self.var_modo, value="video").grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(quadro_op, text="Vídeo MP4",
                        variable=self.var_modo, value="mp4").grid(row=0, column=2, sticky="w")
        ttk.Radiobutton(quadro_op, text="Somente áudio (MP3)",
                        variable=self.var_modo, value="mp3").grid(row=0, column=3, sticky="w")
        ttk.Radiobutton(quadro_op, text="Formato manual:",
                        variable=self.var_modo, value="custom").grid(row=1, column=0, sticky="w", columnspan=2)
        self.var_formato = tk.StringVar(value="bv*+ba/b")
        ttk.Entry(quadro_op, textvariable=self.var_formato, width=28).grid(
            row=1, column=2, columnspan=2, sticky="we", pady=(4, 0))

        ttk.Label(quadro_op, text="Resolução máx.:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.var_res = tk.StringVar(value="(sem limite)")
        ttk.Combobox(quadro_op, textvariable=self.var_res, state="readonly", width=12,
                     values=["(sem limite)", "2160", "1440", "1080", "720", "480", "360"]
                     ).grid(row=2, column=1, sticky="w", pady=(6, 0))

        self.var_playlist = tk.BooleanVar(value=False)
        self.var_legendas = tk.BooleanVar(value=False)
        self.var_thumb = tk.BooleanVar(value=False)
        self.var_meta = tk.BooleanVar(value=True)
        ttk.Checkbutton(quadro_op, text="Baixar playlist inteira",
                        variable=self.var_playlist).grid(row=2, column=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(quadro_op, text="Legendas (pt, en)",
                        variable=self.var_legendas).grid(row=2, column=3, sticky="w", pady=(6, 0))
        ttk.Checkbutton(quadro_op, text="Embutir thumbnail",
                        variable=self.var_thumb).grid(row=3, column=2, sticky="w")
        ttk.Checkbutton(quadro_op, text="Embutir metadados",
                        variable=self.var_meta).grid(row=3, column=3, sticky="w")

        ttk.Label(quadro_op, text="Argumentos extras:").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.var_extras = tk.StringVar()
        ttk.Entry(quadro_op, textvariable=self.var_extras).grid(
            row=4, column=1, columnspan=3, sticky="we", pady=(6, 0))
        for c in range(4):
            quadro_op.columnconfigure(c, weight=1)

        # --- Botões de ação ---
        quadro_btn = ttk.Frame(raiz)
        quadro_btn.pack(fill="x", pady=(10, 0))
        self.btn_info = ttk.Button(quadro_btn, text="Obter informações",
                                   command=self._obter_info)
        self.btn_formatos = ttk.Button(quadro_btn, text="Listar formatos",
                                       command=self._listar_formatos)
        self.btn_baixar = ttk.Button(quadro_btn, text="Baixar",
                                     command=self._baixar)
        self.btn_cancelar = ttk.Button(quadro_btn, text="Cancelar",
                                       command=self._cancelar, state="disabled")
        for b in (self.btn_info, self.btn_formatos, self.btn_baixar, self.btn_cancelar):
            b.pack(side="left", padx=(0, 6))

        # --- Status e progresso ---
        quadro_prog = ttk.Frame(raiz)
        quadro_prog.pack(fill="x", pady=(10, 0))
        self.var_status = tk.StringVar(value="Pronto.")
        ttk.Label(quadro_prog, textvariable=self.var_status).pack(anchor="w")
        self.barra = ttk.Progressbar(quadro_prog, maximum=100.0)
        self.barra.pack(fill="x", pady=(4, 0))
        self.var_detalhe = tk.StringVar(value="")
        ttk.Label(quadro_prog, textvariable=self.var_detalhe).pack(anchor="w")

        # --- Console ---
        quadro_log = ttk.LabelFrame(raiz, text="Saída da CLI", padding=4)
        quadro_log.pack(fill="both", expand=True, pady=(10, 0))
        self.console = scrolledtext.ScrolledText(
            quadro_log, height=12, state="disabled", wrap="word",
            font=("Consolas" if os.name == "nt" else "Monospace", 9))
        self.console.pack(fill="both", expand=True)

    # ------------------------- utilidades de UI --------------------------

    def _colar_url(self) -> None:
        try:
            self.var_url.set(self.clipboard_get().strip())
        except tk.TclError:
            pass

    def _escolher_pasta(self) -> None:
        pasta = filedialog.askdirectory(initialdir=self.var_destino.get())
        if pasta:
            self.var_destino.set(pasta)

    def _log(self, texto: str) -> None:
        self.console.configure(state="normal")
        self.console.insert("end", texto.rstrip("\n") + "\n")
        self.console.see("end")
        self.console.configure(state="disabled")

    def _travar_botoes(self, ocupado: bool) -> None:
        estado = "disabled" if ocupado else "normal"
        for b in (self.btn_info, self.btn_formatos, self.btn_baixar):
            b.configure(state=estado)
        self.btn_cancelar.configure(state="normal" if ocupado else "disabled")

    # ------------------------ construção do comando ----------------------

    def _argumentos_comuns(self) -> list[str]:
        args = ["--newline", "--no-colors", "--ignore-config"]
        args += ["--yes-playlist"] if self.var_playlist.get() else ["--no-playlist"]
        return args

    def _argumentos_download(self) -> list[str]:
        args = self._argumentos_comuns()
        destino = self.var_destino.get().strip()
        if destino:
            args += ["-P", destino]
        args += ["-o", "%(title)s [%(id)s].%(ext)s"]

        modo = self.var_modo.get()
        res = self.var_res.get()
        filtro_res = f"[height<={res}]" if res.isdigit() else ""
        if modo == "video":
            args += ["-f", f"bv*{filtro_res}+ba/b{filtro_res}"]
        elif modo == "mp4":
            args += ["-f", f"bv*{filtro_res}+ba/b{filtro_res}",
                     "--merge-output-format", "mp4", "--remux-video", "mp4"]
        elif modo == "mp3":
            args += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
        else:  # custom
            formato = self.var_formato.get().strip()
            if formato:
                args += ["-f", formato]

        if self.var_legendas.get():
            args += ["--write-subs", "--write-auto-subs", "--sub-langs", "pt.*,en.*"]
        if self.var_thumb.get():
            args += ["--embed-thumbnail"]
        if self.var_meta.get():
            args += ["--embed-metadata"]

        extras = self.var_extras.get().strip()
        if extras:
            args += shlex.split(extras)
        return args

    # --------------------------- ações (worker) --------------------------

    def _executar(self, args: list[str], modo: str) -> None:
        """Dispara o subprocesso em thread de trabalho. `modo` define o
        tratamento da saída: 'download', 'info_json' ou 'texto'."""
        url = self.var_url.get().strip()
        if not url:
            messagebox.showwarning("URL ausente", "Informe a URL do vídeo ou playlist.")
            return
        if self.processo is not None:
            messagebox.showinfo("Em execução", "Há um processo em andamento; cancele-o primeiro.")
            return

        comando = self.cmd_base + args + ["--", url]
        self._log("\n$ " + " ".join(shlex.quote(p) for p in comando))
        self.barra["value"] = 0
        self.var_detalhe.set("")
        self._travar_botoes(True)
        self.var_status.set("Executando…")

        self.worker = threading.Thread(
            target=self._worker_processo, args=(comando, modo), daemon=True)
        self.worker.start()

    def _worker_processo(self, comando: list[str], modo: str) -> None:
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self.processo = subprocess.Popen(
                comando,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=flags,
            )
        except OSError as exc:
            self.fila.put(Msg("log", f"ERRO ao iniciar o processo: {exc}"))
            self.fila.put(Msg("fim", 1))
            return

        acumulado: list[str] = []
        assert self.processo.stdout is not None
        for linha in self.processo.stdout:
            if modo == "info_json":
                acumulado.append(linha)      # JSON pode vir em linha única longa
                continue
            self._interpretar_linha(linha, modo, acumulado)

        codigo = self.processo.wait()
        if modo == "info_json" and codigo == 0:
            self.fila.put(Msg("info_json", "".join(acumulado)))
        self.fila.put(Msg("fim", codigo))

    def _interpretar_linha(self, linha: str, modo: str, acumulado: list[str]) -> None:
        """Interpreta uma linha de stdout e publica mensagens na fila."""
        texto = linha.rstrip("\n")
        if not texto:
            return

        m = RE_PROGRESSO.search(texto)
        if m:
            pct = float(m.group("pct"))
            detalhe = []
            if m.group("total"):
                detalhe.append(f"de {m.group('total')}")
            if m.group("vel"):
                detalhe.append(f"a {m.group('vel')}")
            if m.group("eta"):
                detalhe.append(f"ETA {m.group('eta')}")
            self.fila.put(Msg("progresso", pct, " ".join(detalhe)))
            return  # linhas de progresso não poluem o console

        if (m := RE_ITEM_PLAYLIST.search(texto)):
            self.fila.put(Msg("status", f"Playlist: item {m.group('n')} de {m.group('total')}"))
        elif (m := RE_DESTINO.search(texto)):
            self.fila.put(Msg("status", f"Baixando: {Path(m.group('arquivo')).name}"))
        elif (m := RE_JA_BAIXADO.search(texto)):
            self.fila.put(Msg("status", "Arquivo já baixado anteriormente."))
        elif RE_POSPROC.search(texto):
            self.fila.put(Msg("status", "Pós-processamento (ffmpeg)…"))
        elif (m := RE_ERRO.match(texto)):
            self.fila.put(Msg("status", f"Erro: {m.group('msg')[:90]}"))

        self.fila.put(Msg("log", texto))

    # ------------------------ ações (interface) --------------------------

    def _baixar(self) -> None:
        self._executar(self._argumentos_download(), "download")

    def _listar_formatos(self) -> None:
        self._executar(self._argumentos_comuns() + ["-F"], "texto")

    def _obter_info(self) -> None:
        self._executar(self._argumentos_comuns() + ["-J", "--no-warnings"], "info_json")

    def _cancelar(self) -> None:
        if self.processo and self.processo.poll() is None:
            self.processo.terminate()
            self.var_status.set("Cancelando…")

    # ----------------------- drenagem da fila (UI) -----------------------

    def _drenar_fila(self) -> None:
        try:
            while True:
                msg = self.fila.get_nowait()
                self._tratar_msg(msg)
        except queue.Empty:
            pass
        self.after(100, self._drenar_fila)

    def _tratar_msg(self, msg: Msg) -> None:
        if msg.tipo == "log":
            self._log(str(msg.dado))
        elif msg.tipo == "progresso":
            self.barra["value"] = float(msg.dado)          # type: ignore[arg-type]
            self.var_detalhe.set(f"{msg.dado}% {msg.extra or ''}")
        elif msg.tipo == "status":
            self.var_status.set(str(msg.dado))
        elif msg.tipo == "info_json":
            self._exibir_info(str(msg.dado))
        elif msg.tipo == "fim":
            codigo = int(msg.dado)                          # type: ignore[arg-type]
            self.processo = None
            self._travar_botoes(False)
            if codigo == 0:
                self.barra["value"] = 100
                self.var_status.set("Concluído com êxito.")
            elif codigo < 0 or (codigo == 1 and self.var_status.get().startswith("Cancelando")):
                self.var_status.set("Cancelado pelo usuário.")
            else:
                self.var_status.set(f"Encerrado com código {codigo}; verifique o console.")

    def _exibir_info(self, bruto: str) -> None:
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError:
            self._log("Não foi possível decodificar o JSON retornado por -J.")
            return

        entradas = dados.get("entries") or [dados]
        self._log("—" * 60)
        for e in entradas[:25]:
            if e is None:
                continue
            dur = e.get("duration")
            dur_fmt = f"{int(dur)//60}:{int(dur)%60:02d}" if dur else "?"
            self._log(f"Título   : {e.get('title', '?')}")
            self._log(f"Canal    : {e.get('uploader', e.get('channel', '?'))}")
            self._log(f"Duração  : {dur_fmt}   |  Visualizações: {e.get('view_count', '?')}")
            self._log(f"ID       : {e.get('id', '?')}   |  Ext: {e.get('ext', '?')}")
            self._log("—" * 60)
        if len(entradas) > 25:
            self._log(f"(… e mais {len(entradas) - 25} itens na playlist)")

    # ------------------------------ ciclo --------------------------------

    def _ao_fechar(self) -> None:
        if self.processo and self.processo.poll() is None:
            if not messagebox.askyesno(
                    "Processo em execução",
                    "Há um download em andamento. Encerrar mesmo assim?"):
                return
            self.processo.terminate()
        self.destroy()


if __name__ == "__main__":
    YtDlpGui().mainloop()
