import { useState, useRef, useCallback, useEffect } from 'react';
import SourcesPanel from '../components/SourcesPanel';
import ChatPanel from '../components/ChatPanel';
import * as api from '../api';

interface Props { onLogout: () => void; }

export default function Workspace({ onLogout }: Props) {
  const [leftWidth, setLeftWidth] = useState(340);
  const [isDragging, setIsDragging] = useState(false);
  const [selectedCollectionId, setSelectedCollectionId] = useState<string>('all');
  const [statsRefreshKey, setStatsRefreshKey] = useState(0);
  const [statusMsg, setStatusMsg] = useState('已登录');
  const containerRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  // Poll login status for detailed message
  useEffect(() => {
    const poll = setInterval(async () => {
      try {
        const s = await api.loginStatus();
        if (s.message) setStatusMsg(s.message);
      } catch {}
    }, 3000);
    return () => clearInterval(poll);
  }, []);

  useEffect(() => {
    if (!isDragging) return;
    const move = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const r = containerRef.current.getBoundingClientRect();
      setLeftWidth(Math.max(240, Math.min(r.width * 0.5, e.clientX - r.left)));
    };
    const up = () => setIsDragging(false);
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    return () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isDragging]);

  return (
    <div className="h-screen flex flex-col bg-[var(--color-bg)]">
      {/* Top Bar */}
      <header className="flex items-center justify-between px-7 py-3.5 bg-white/80 backdrop-blur border-b border-[var(--color-border)] flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br from-accent to-amber shadow-lg shadow-accent/20">
            <span className="font-display text-white text-xl font-bold">D</span>
          </div>
          <div>
            <h1 className="font-display text-lg text-[var(--color-ink)]">DouyinMind · 收藏夹知识库</h1>
            <span className="text-[10px] text-[var(--color-ink-muted)] tracking-[0.15em] uppercase">Save · Learn · Ask</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs max-w-md truncate"
            style={{ backgroundColor: 'rgba(91,140,90,0.12)', color: 'var(--color-success)' }}>
            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: 'var(--color-success)' }} /> {statusMsg}
          </span>
          <button onClick={onLogout} className="w-8 h-8 rounded-full border border-[var(--color-border)] bg-white/70 flex items-center justify-center hover:border-accent/50 transition-colors text-sm text-[var(--color-ink-muted)]">
            ⏻
          </button>
        </div>
      </header>

      {/* Main Area */}
      <div ref={containerRef} className="flex-1 flex min-h-0" style={{ userSelect: isDragging ? 'none' : undefined }}>
        {/* Left Panel */}
        <aside style={{ width: leftWidth, flexShrink: 0 }} className="h-full">
          <SourcesPanel
            onBuildDone={() => setStatsRefreshKey(k => k + 1)}
            selectedId={selectedCollectionId}
            onSelectCollection={setSelectedCollectionId}
            statsRefreshKey={statsRefreshKey}
          />
        </aside>

        {/* Resizer */}
        <div onMouseDown={handleMouseDown} className="w-2 flex-shrink-0 cursor-col-resize relative group flex items-center justify-center">
          <div className="w-1 h-8 rounded-full bg-[var(--color-border)] group-hover:h-14 group-hover:bg-accent transition-all" />
        </div>

        {/* Right Panel */}
        <main className="flex-1 h-full min-w-0">
          <ChatPanel collectionId={selectedCollectionId} statsRefreshKey={statsRefreshKey} />
        </main>
      </div>
    </div>
  );
}
