// src/lib/api.ts
// Cliente HTTP para o backend Python local (porta 17432)

const BASE = "http://127.0.0.1:17432";

export interface DownloadRequest {
  url: string;
  format_id: string;
  quality: string;
  output_dir?: string;
}

export interface QueueItem {
  id: string;
  url: string;
  title: string;
  channel: string;
  format_id: string;
  quality: string;
  status: "queued" | "downloading" | "done" | "error";
  progress: number;
  speed: string;
  error: string;
  output_dir: string;
}

export const api = {
  async addDownload(req: DownloadRequest): Promise<{ id: string }> {
    const res = await fetch(`${BASE}/api/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async removeItem(id: string): Promise<void> {
    await fetch(`${BASE}/api/queue/${id}`, { method: "DELETE" });
  },

  async getInfo(url: string): Promise<{ title: string; thumbnail: string; duration: number; channel: string }> {
    const res = await fetch(`${BASE}/api/info?url=${encodeURIComponent(url)}`);
    return res.json();
  },

  /** EventSource para progresso em tempo real */
  streamQueue(onData: (items: QueueItem[]) => void): EventSource {
    const es = new EventSource(`${BASE}/api/queue/stream`);
    es.onmessage = (e) => {
      try { onData(JSON.parse(e.data)); } catch {}
    };
    return es;
  },
};
