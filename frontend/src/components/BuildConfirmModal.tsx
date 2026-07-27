import { useState, useEffect } from 'react';
import * as api from '../api';

interface Props {
  onClose: () => void;
  onConfirm: (selectedIds: string[]) => void;
  pendingCount: number;
}

export default function BuildConfirmModal({ onClose, onConfirm, pendingCount }: Props) {
  const [videos, setVideos] = useState<api.VideoItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await api.listCollectionVideos('all', 1, 100);
        if (r.success) {
          const pending = r.items.filter(v => v.status === 'pending');
          setVideos(pending);
          setSelected(new Set(pending.map(v => v.platform_item_id)));
        }
      } catch (e) { console.error('加载待入库视频失败:', e); }
      setLoading(false);
    })();
  }, []);

  const toggleOne = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === videos.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(videos.map(v => v.platform_item_id)));
    }
  };

  const handleConfirm = () => {
    setBuilding(true);
    onConfirm([...selected]);
  };

  const allChecked = videos.length > 0 && selected.size === videos.length;
  const hasSelection = selected.size > 0;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-[var(--color-panel)] rounded-2xl w-[460px] max-h-[80vh] flex flex-col shadow-2xl" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="px-6 pt-6 pb-4">
          <h2 className="font-display text-xl text-[var(--color-ink)]">确认入库</h2>
          <p className="text-xs text-[var(--color-ink-muted)] mt-1">
            选择要入库的视频，将执行：下载音频 → 语音转写 → 向量化
          </p>
        </div>

        {/* Select All bar */}
        <div className="flex items-center justify-between px-6 py-2">
          <button onClick={toggleAll} className="flex items-center gap-2 text-xs text-[var(--color-ink-soft)] hover:text-accent transition-colors">
            <span className={`text-base ${allChecked ? 'text-accent' : 'text-[var(--color-ink-muted)]'}`}>
              {allChecked ? '☑' : '☐'}
            </span>
            全选
          </button>
          <span className="text-xs text-accent font-bold">
            已选 {selected.size} / {videos.length} 个
          </span>
        </div>

        {/* Video list */}
        <div className="flex-1 overflow-y-auto max-h-[40vh] mx-6 border border-[var(--color-border)] rounded-xl divide-y divide-[var(--color-border)]">
          {loading ? (
            <p className="text-center text-xs text-[var(--color-ink-muted)] py-12">加载中...</p>
          ) : videos.length === 0 ? (
            <p className="text-center text-xs text-[var(--color-ink-muted)] py-12">没有待入库的视频</p>
          ) : (
            videos.map(v => {
              const checked = selected.has(v.platform_item_id);
              return (
                <button
                  key={v.platform_item_id}
                  onClick={() => toggleOne(v.platform_item_id)}
                  className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-black/[0.02] transition-colors"
                >
                  <span className={`text-base flex-shrink-0 ${checked ? 'text-accent' : 'text-[var(--color-ink-muted)]'}`}>
                    {checked ? '☑' : '☐'}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-[var(--color-ink)] truncate">{v.title}</p>
                    <p className="text-[11px] text-[var(--color-ink-muted)]">
                      @{v.author}{v.duration ? ` · ${Math.floor(v.duration / 60)}:${String(v.duration % 60).padStart(2, '0')}` : ''}
                    </p>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Warning */}
        <div className="mx-6 mt-3 px-3 py-2 rounded-xl text-xs text-[var(--color-amber)] bg-amber-light flex items-center gap-2">
          <span>⚠️</span> 入库将调用 DashScope ASR + Embedding API，可能产生少量费用。
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3 px-6 py-4">
          <button onClick={onClose} className="px-5 py-2 rounded-full text-sm text-[var(--color-ink-soft)] border border-[var(--color-border)] hover:bg-black/3 transition-colors">
            取消
          </button>
          <button
            onClick={handleConfirm}
            disabled={building || !hasSelection}
            className="px-5 py-2 rounded-full bg-gradient-to-r from-accent to-accent-hover text-white text-sm font-bold shadow-md shadow-accent/20 hover:shadow-lg transition-all disabled:opacity-40"
          >
            {building ? '⏳ 入库中...' : `确认入库 (${selected.size})`}
          </button>
        </div>
      </div>
    </div>
  );
}
