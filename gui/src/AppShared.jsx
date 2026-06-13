// ============================================================
// yt-dlp-GUI — base compartilhada entre as variações
// Janela desktop, ícones, dados de formato/qualidade e a
// simulação da fila de downloads.
// ============================================================

const YDG_FORMAT_GROUPS = [
{
  label: 'Vídeo',
  items: [
  { id: 'mp4', name: 'MP4', desc: 'H.264 + AAC', kind: 'video' },
  { id: 'webm', name: 'WebM', desc: 'VP9 + Opus', kind: 'video' },
  { id: 'mkv', name: 'MKV', desc: 'melhor stream', kind: 'video' }]

},
{
  label: 'Áudio',
  items: [
  { id: 'm4a', name: 'M4A', desc: 'AAC original', kind: 'audio' },
  { id: 'mp3', name: 'MP3', desc: 'convertido', kind: 'audio' },
  { id: 'opus', name: 'Opus', desc: 'sem conversão', kind: 'audio' },
  { id: 'wav', name: 'WAV', desc: 'sem compressão', kind: 'audio' }]

}];


const YDG_ALL_FORMATS = YDG_FORMAT_GROUPS.flatMap(function (g) {return g.items;});

function ydgFormat(id) {
  return YDG_ALL_FORMATS.find(function (f) {return f.id === id;}) || YDG_ALL_FORMATS[0];
}

const YDG_VIDEO_QUALITIES = ['Melhor', '2160p', '1440p', '1080p', '720p', '480p'];
const YDG_AUDIO_QUALITIES = ['Melhor', '320 kbps', '256 kbps', '192 kbps', '128 kbps'];

function ydgQualities(formatId) {
  return ydgFormat(formatId).kind === 'audio' ? YDG_AUDIO_QUALITIES : YDG_VIDEO_QUALITIES;
}

const YDG_FAKE_VIDEOS = [
{ title: 'Como compilar o yt-dlp do zero — guia completo', channel: 'Terminal Brasil', duration: '18:42', size: '312 MB' },
{ title: 'Mix de 1 hora para programar sem interrupções', channel: 'Beats de Estúdio', duration: '1:02:11', size: '89 MB' },
{ title: 'Os 5 melhores teclados mecânicos de 2026', channel: 'Bancada Tech', duration: '14:05', size: '248 MB' },
{ title: 'A história do formato MP4 — documentário', channel: 'Arquivo Aberto', duration: '42:30', size: '1.1 GB' },
{ title: 'Engenharia de codecs — entrevista completa', channel: 'Conversa Técnica', duration: '55:18', size: '940 MB' },
{ title: 'Ray tracing explicado em 12 minutos', channel: 'Pixel a Pixel', duration: '12:08', size: '201 MB' }];


function ydgIsValidUrl(v) {
  return /(youtube\.com|youtu\.be)\//i.test(v.trim());
}

// ---------- Ícones (traço simples, 1.5px) ----------
function YdgIcon({ name, size = 16, stroke = 1.5, style }) {
  const paths = {
    download: <g><path d="M8 2.5v7.5" /><path d="M4.5 7L8 10.5L11.5 7" /><path d="M2.5 12.5h11" /></g>,
    chevron: <path d="M4 6l4 4 4-4" />,
    link: <g><path d="M6.5 9.5l3-3" /><path d="M7.5 4.5l1-1a2.5 2.5 0 013.5 3.5l-1 1" /><path d="M8.5 11.5l-1 1A2.5 2.5 0 014 9l1-1" /></g>,
    check: <path d="M3 8.5L6.5 12L13 4.5" />,
    x: <g><path d="M4 4l8 8" /><path d="M12 4l-8 8" /></g>,
    clock: <g><circle cx="8" cy="8" r="5.5" /><path d="M8 5.5V8l2 1.5" /></g>,
    pause: <g><path d="M6 4.5v7" /><path d="M10 4.5v7" /></g>,
    folder: <path d="M2.5 4.5a1 1 0 011-1h3l1.5 2h4.5a1 1 0 011 1v5a1 1 0 01-1 1h-9a1 1 0 01-1-1v-7z" />,
    play: <path d="M5.5 4l6 4-6 4V4z" />
  };
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor"
    strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" style={style} aria-hidden="true">
      {paths[name]}
    </svg>);

}

// ---------- Moldura de janela desktop ----------
function YdgWindow({ label, children, height }) {
  return (
    <div className="ydg-win" data-screen-label={label} style={{ height: height }}>
      <div className="ydg-tbar">
        <div className="ydg-tbar-left">
          <div className="ydg-mark"><YdgIcon name="download" size={11} stroke={2} /></div>
          <span className="ydg-tbar-title" style={{ fontFamily: "-apple-system", fontSize: "6px" }}>yt-dlp-GUI</span>
          <span className="ydg-tbar-ver">v2.1.0</span>
        </div>
        <div className="ydg-tbar-btns">
          <div className="ydg-tbtn"><svg width="10" height="10" viewBox="0 0 10 10"><path d="M1 5h8" stroke="currentColor" strokeWidth="1.2" /></svg></div>
          <div className="ydg-tbtn"><svg width="10" height="10" viewBox="0 0 10 10"><rect x="1.5" y="1.5" width="7" height="7" fill="none" stroke="currentColor" strokeWidth="1.2" /></svg></div>
          <div className="ydg-tbtn ydg-tbtn-close"><svg width="10" height="10" viewBox="0 0 10 10"><path d="M1.5 1.5l7 7M8.5 1.5l-7 7" stroke="currentColor" strokeWidth="1.2" /></svg></div>
        </div>
      </div>
      <div className="ydg-body">{children}</div>
    </div>);

}

// ---------- Simulação da fila de downloads ----------
function ydgMakeItem(video, formatId, quality, status, progress) {
  return {
    id: 'i' + Math.random().toString(36).slice(2),
    title: video.title, channel: video.channel, duration: video.duration, size: video.size,
    formatId: formatId, quality: quality,
    status: status, progress: progress, speed: status === 'downloading' ? '6.4 MB/s' : ''
  };
}

function ydgInitialQueue() {
  return [
  ydgMakeItem(YDG_FAKE_VIDEOS[0], 'mp4', '1080p', 'downloading', 47),
  ydgMakeItem(YDG_FAKE_VIDEOS[1], 'm4a', 'Melhor', 'queued', 0),
  ydgMakeItem(YDG_FAKE_VIDEOS[2], 'mp4', '720p', 'done', 100)];

}

function useYdgQueue() {
  const [items, setItems] = React.useState(ydgInitialQueue);
  React.useEffect(function () {
    const t = setInterval(function () {
      setItems(function (prev) {
        let changed = false;
        let next = prev.map(function (it) {
          if (it.status !== 'downloading') return it;
          changed = true;
          const p = Math.min(100, it.progress + 0.5 + Math.random() * 1.8);
          return Object.assign({}, it, {
            progress: p,
            status: p >= 100 ? 'done' : 'downloading',
            speed: p >= 100 ? '' : (3 + Math.random() * 9).toFixed(1) + ' MB/s'
          });
        });
        const active = next.filter(function (i) {return i.status === 'downloading';}).length;
        if (active < 2) {
          const qi = next.findIndex(function (i) {return i.status === 'queued';});
          if (qi !== -1) {
            next = next.slice();
            next[qi] = Object.assign({}, next[qi], { status: 'downloading' });
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }, 380);
    return function () {clearInterval(t);};
  }, []);

  const add = React.useCallback(function (formatId, quality) {
    const video = YDG_FAKE_VIDEOS[Math.floor(Math.random() * YDG_FAKE_VIDEOS.length)];
    setItems(function (prev) {
      return [ydgMakeItem(video, formatId, quality, 'queued', 0)].concat(prev);
    });
  }, []);

  const remove = React.useCallback(function (id) {
    setItems(function (prev) {return prev.filter(function (i) {return i.id !== id;});});
  }, []);

  return { items: items, add: add, remove: remove };
}

// ---------- Barra de entrada: estado comum (url + validação) ----------
function useYdgInput(onSubmit) {
  const [url, setUrl] = React.useState('');
  const [error, setError] = React.useState(false);
  const submit = function () {
    if (!ydgIsValidUrl(url)) {
      setError(true);
      setTimeout(function () {setError(false);}, 600);
      return;
    }
    onSubmit();
    setUrl('');
  };
  return {
    url: url,
    error: error,
    onChange: function (e) {setUrl(e.target.value);setError(false);},
    onKeyDown: function (e) {if (e.key === 'Enter') submit();},
    submit: submit
  };
}

// Fecha menus ao clicar fora
function useYdgClickOutside(ref, onClose) {
  React.useEffect(function () {
    function handler(e) {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    }
    document.addEventListener('mousedown', handler);
    return function () {document.removeEventListener('mousedown', handler);};
  }, [onClose]);
}

Object.assign(window, {
  YDG_FORMAT_GROUPS, YDG_ALL_FORMATS, YDG_VIDEO_QUALITIES, YDG_AUDIO_QUALITIES,
  ydgFormat, ydgQualities, ydgIsValidUrl,
  YdgIcon, YdgWindow,
  useYdgQueue, useYdgInput, useYdgClickOutside
});