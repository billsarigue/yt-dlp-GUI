// ============================================================
// Variação A — "Barra integrada"
// Formato acoplado dentro da própria barra; Download anexado
// na extremidade. Qualidade num seletor separado abaixo.
// Fila em cartões com miniatura.
// ============================================================

function YdgFormatMenuA({ open, current, onPick, onClose, anchorRef }) {
  useYdgClickOutside(anchorRef, onClose);
  if (!open) return null;
  return (
    <div className="ydg-menu" style={{ right: 0, top: 'calc(100% + 6px)', width: 232 }}>
      {YDG_FORMAT_GROUPS.map(function (group) {
        return (
          <div key={group.label}>
            <div className="ydg-menu-h">{group.label}</div>
            {group.items.map(function (f) {
              const active = f.id === current;
              return (
                <button key={f.id} className={'ydg-menu-item' + (active ? ' is-active' : '')}
                onClick={function () {onPick(f.id);onClose();}}>
                  <span className="ydg-menu-name">{f.name}</span>
                  <span className="ydg-menu-desc">{f.desc}</span>
                  {active ? <YdgIcon name="check" size={13} style={{ color: 'var(--ydg-accent)' }} /> : null}
                </button>);

            })}
          </div>);

      })}
    </div>);

}

function YdgQualityPillA({ formatId, quality, setQuality }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef(null);
  useYdgClickOutside(ref, function () {setOpen(false);});
  const opts = ydgQualities(formatId);
  return (
    <div className="ydg-rel" ref={ref}>
      <button className="ydg-pill" onClick={function () {setOpen(!open);}}>
        <span className="ydg-pill-label">Qualidade</span>
        <span className="ydg-pill-value">{quality}</span>
        <YdgIcon name="chevron" size={12} style={{ color: 'var(--ydg-text3)' }} />
      </button>
      {open ?
      <div className="ydg-menu" style={{ left: 0, top: 'calc(100% + 6px)', width: 160 }}>
          {opts.map(function (q) {
          return (
            <button key={q} className={'ydg-menu-item' + (q === quality ? ' is-active' : '')}
            onClick={function () {setQuality(q);setOpen(false);}}>
                <span className="ydg-menu-name" style={{ fontWeight: 450 }}>{q}</span>
                {q === quality ? <YdgIcon name="check" size={13} style={{ color: 'var(--ydg-accent)' }} /> : null}
              </button>);

        })}
        </div> :
      null}
    </div>);

}

function YdgQueueCardA({ item, onRemove }) {
  const f = ydgFormat(item.formatId);
  return (
    <div className="ydg-card">
      <div className="ydg-thumb">
        <YdgIcon name={f.kind === 'audio' ? 'pause' : 'play'} size={14} style={{ color: 'var(--ydg-text3)', opacity: 0.9 }} />
      </div>
      <div className="ydg-card-mid">
        <div className="ydg-card-title">{item.title}</div>
        <div className="ydg-card-meta">
          <span className="ydg-badge">{f.name}</span>
          <span>{item.quality}</span>
          <span>·</span>
          <span>{item.size}</span>
          {item.status === 'downloading' ? <span className="ydg-speed">{item.speed}</span> : null}
          {item.status === 'queued' ? <span className="ydg-queued"><YdgIcon name="clock" size={11} /> na fila</span> : null}
          {item.status === 'done' ? <span className="ydg-done"><YdgIcon name="check" size={11} /> concluído</span> : null}
        </div>
        <div className="ydg-prog">
          <div className={'ydg-prog-fill' + (item.status === 'done' ? ' is-done' : '')}
          style={{ width: item.progress + '%' }}></div>
        </div>
      </div>
      <div className="ydg-card-side">
        <span className="ydg-pct">{Math.floor(item.progress)}%</span>
        <button className="ydg-icon-btn" title="Remover" onClick={function () {onRemove(item.id);}}>
          <YdgIcon name="x" size={12} />
        </button>
      </div>
    </div>);

}

function YdgVariationA() {
  const [formatId, setFormatId] = React.useState('mp4');
  const [quality, setQuality] = React.useState('1080p');
  const [menuOpen, setMenuOpen] = React.useState(false);
  const queue = useYdgQueue();
  const input = useYdgInput(function () {queue.add(formatId, quality);});
  const fmtRef = React.useRef(null);

  function pickFormat(id) {
    setFormatId(id);
    setQuality(ydgQualities(id)[ydgFormat(id).kind === 'audio' ? 0 : 3] || 'Melhor');
  }

  return (
    <YdgWindow label="A — Barra integrada" height="100%">
      <div className="ydg-center" style={{ paddingTop: 48, margin: "40px 89px 0px" }}>
        <div className={'ydg-bar' + (input.error ? ' is-error' : '')}>
          <span className="ydg-bar-icon"><YdgIcon name="link" size={15} /></span>
          <input className="ydg-input" type="text" value={input.url}
          placeholder="Cole o link do YouTube aqui…"
          onChange={input.onChange} onKeyDown={input.onKeyDown} spellCheck="false" />
          <div className="ydg-rel" ref={fmtRef} style={{ alignSelf: 'stretch', display: 'flex' }}>
            <button className="ydg-fmt-trigger" onClick={function () {setMenuOpen(!menuOpen);}}>
              <span>{ydgFormat(formatId).name}</span>
              <YdgIcon name="chevron" size={12} style={{ color: 'var(--ydg-text3)' }} />
            </button>
            <YdgFormatMenuA open={menuOpen} current={formatId} onPick={pickFormat}
            onClose={function () {setMenuOpen(false);}} anchorRef={fmtRef} />
          </div>
          <button className="ydg-dl-btn" onClick={input.submit}>
            <YdgIcon name="download" size={15} stroke={1.8} />
            <span>Download</span>
          </button>
        </div>

        <div className="ydg-under-bar">
          <YdgQualityPillA formatId={formatId} quality={quality} setQuality={setQuality} />
          <div className="ydg-dest">
            <YdgIcon name="folder" size={13} />
            <span>~/Downloads</span>
          </div>
        </div>

        <div className="ydg-queue">
          <div className="ydg-queue-h">
            <span>Downloads</span>
            <span className="ydg-queue-count">{queue.items.length}</span>
          </div>
          <div className="ydg-cards">
            {queue.items.map(function (item) {
              return <YdgQueueCardA key={item.id} item={item} onRemove={queue.remove} />;
            })}
          </div>
        </div>
      </div>
    </YdgWindow>);

}

window.YdgVariationA = YdgVariationA;