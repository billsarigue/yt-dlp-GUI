// src/hooks/useDownloadQueue.ts
import { useEffect, useRef, useState } from "react";
import { api, QueueItem } from "../lib/api";

export function useDownloadQueue() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    // Conecta ao SSE do backend
    esRef.current = api.streamQueue(setItems);
    return () => esRef.current?.close();
  }, []);

  const add = async (url: string, format_id: string, quality: string, output_dir = "") => {
    // Busca título antes de enfileirar
    const info = await api.getInfo(url).catch(() => ({ title: url, thumbnail: "", duration: 0, channel: "" }));
    await api.addDownload({ url, format_id, quality, output_dir });
    return info;
  };

  const remove = (id: string) => api.removeItem(id);

  return { items, add, remove };
}
