import { useState, useEffect, useCallback } from 'react';
import * as api from '../api';
import BuildConfirmModal from './BuildConfirmModal';

interface Props {
  onBuildDone: () => void;
  selectedId: string;
  onSelectCollection: (id: string) => void;
  statsRefreshKey: number;
}

export default function SourcesPanel({ onBuildDone, selectedId, onSelectCollection, statsRefreshKey }: Props) {
  const [collections, setCollections] = useState<api.CollectionItem[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [syncing, setSyncing] = useState(false);
  const [building, setBuilding] = useState(false);
  const [buildProgress, setBuildProgress] = useState(0);
  const [buildTotal, setBuildTotal] = useState(0);
  const [buildMessage, setBuildMessage] = useState('');
  const [showBuildConfirm, setShowBuildConfirm] = useState(false);
  const [sessions, setSessions] = useState<api.SessionItem[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandedVideos, setExpandedVideos] = useState<api.VideoItem[]>([]);
  const [loadingVideos, setLoadingVideos] = useState(false);

  const fetchCollections = useCallback(async () => {
    try {
      const r = await api.listCollections();
      if (r.success) setCollections(r.items);
    } catch {}
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const r = await api.getKnowledgeStats();
      if (r.success) setStats(r);
    } catch {}
  }, []);

  const fetchSessions = useCallback(async () => {
    try {
      const r = await api.listSessions();
      if (r.success) setSessions(r.items);
    } catch {}
  }, []);

  useEffect(() => { fetchCollections(); fetchStats(); fetchSessions(); }, [fetchCollections, fetchStats, fetchSessions, statsRefreshKey]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      const r = await api.syncFavorites();
      if (r.success) {
        await fetchCollections();
      } else {
        alert(r.message || '同步失败');
      }
    } catch (e: any) {
      alert('同步失败: ' + e.message);
    }
    setSyncing(false);
  };

  const handleBuild = async (selectedIds?: string[]) => {
    setBuilding(true);
    setBuildProgress(0);
    setBuildTotal(0);
    setBuildMessage('准备中...');
    try {
      const r = await api.syncKnowledge(selectedIds);
      if (r.success && r.task_id) {
        const poll = setInterval(async () => {
          try {
            const p = await api.getSyncProgress(r.task_id!);
            if (!p) return;
            setBuildProgress(p.progress || 0);
            setBuildTotal(p.total || 0);
            if (p.message) setBuildMessage(p.message);
            if (p.status === 'done' || p.status === 'failed') {
              clearInterval(poll);
              setBuilding(false);
              onBuildDone();
              fetchStats();
            }
          } catch {}
        }, 800);
      }
    } catch (e: any) {
      alert('入库失败: ' + e.message);
      setBuilding(false);
    }
  };

  const handleCollectionClick = async (collectionId: string) => {
    onSelectCollection(collectionId);
    if (expandedId === collectionId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(collectionId);
    setLoadingVideos(true);
    try {
      const r = await api.listCollectionVideos(collectionId, 1, 10);
      if (r.success) setExpandedVideos(r.items);
    } catch {}
    setLoadingVideos(false);
  };

  const handleExport = (platformItemId: string, mode: 'original' | 'ai') => {
    const url = `/api/knowledge/export/${platformItemId}?mode=${mode}`;
    window.open(url, '_blank');
  };

  const handleDelete = async (platformItemId: string) => {
    if (!confirm('确定要删除这个视频的入库数据吗？\n\n删除后可重新入库。')) return;
    try {
      await api.deleteVideo(platformItemId);
      fetchStats();
      // 刷新当前展开的视频列表
      if (expandedId) {
        const r = await api.listCollectionVideos(expandedId, 1, 100);
        if (r.success) setExpandedVideos(r.items);
      }
    } catch (e: any) {
      alert('删除失败: ' + e.message);
    }
  };

  const doneCount = stats?.video_cache?.done ?? 0;
  const failedCount = stats?.video_cache?.failed ?? 0;
  const processingCount = (stats?.video_cache?.downloading ?? 0) + (stats?.video_cache?.transcribing ?? 0);
  const totalCount = Object.values(stats?.video_cache ?? {}).reduce((a: number, b: any) => a + b, 0) as number;
  const pendingCount = stats?.video_cache?.pending ?? 0;
  const isStuck = processingCount > 0 || (failedCount > 0 && pendingCount === 0 && processingCount === 0);

  // 页面加载时检测是否有进行中的任务
  useEffect(() => {
    if (processingCount > 0) {
      setBuilding(true);
      setBuildProgress(0);
      setBuildTotal(processingCount);
      setBuildMessage(`${processingCount} 个视频卡在处理中，建议重置后重试`);
    }
  }, [processingCount]);

  return (
    <div className="h-full flex flex-col bg-[var(--color-panel)] border-r border-[var(--color-border)]">
      <div className="flex-1 flex flex-col min-h-0 p-4 gap-3 overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-[var(--color-ink)]">📁 我的收藏夹</h2>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-1 px-3 py-1.5 rounded-full text-xs text-[var(--color-ink-soft)] bg-black/3 hover:bg-black/6 transition-colors disabled:opacity-50"
          >
            {syncing ? '⏳' : '🔄'} 同步
          </button>
        </div>

        <hr className="border-[var(--color-border)]" />

        {/* Collections */}
        <div className="flex flex-col gap-2">
          {collections.map(col => {
            const isSelected = selectedId === col.collection_id;
            const isExpanded = expandedId === col.collection_id;
            return (
              <div key={col.collection_id}>
                <button
                  onClick={() => handleCollectionClick(col.collection_id)}
                  className={`w-full text-left p-2.5 rounded-xl transition-all border ${
                    isSelected
                      ? 'border-accent/40 bg-accent-light shadow-sm'
                      : 'border-transparent hover:border-[var(--color-border)] hover:bg-white/60'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-[var(--color-ink)] truncate flex-1">{col.title}</span>
                    <span className="text-[11px] text-[var(--color-ink-muted)] ml-2 flex-shrink-0">
                      {col.video_count} 个 {isExpanded ? '▲' : '▼'}
                    </span>
                  </div>
                </button>
                {/* Expanded video list */}
                {isExpanded && (
                  <div className="ml-3 mt-1 border-l-2 border-[var(--color-border)] pl-3 py-1">
                    {loadingVideos ? (
                      <p className="text-xs text-[var(--color-ink-muted)] py-2">加载中...</p>
                    ) : expandedVideos.length === 0 ? (
                      <p className="text-xs text-[var(--color-ink-muted)] py-2">暂无视频，请先同步</p>
                    ) : (
                      expandedVideos.map(v => (
                        <div key={v.platform_item_id} className="flex items-center justify-between py-1.5 gap-1">
                          <span className="text-xs text-[var(--color-ink)] truncate flex-1">{v.title}</span>
                          {v.status === 'done' && (
                            <div className="flex gap-1 flex-shrink-0">
                              <button onClick={() => handleExport(v.platform_item_id, 'original')}
                                className="text-[10px] px-1.5 py-0.5 rounded hover:bg-black/5 transition-colors text-[var(--color-ink-muted)]"
                                title="导出原始转写">📄</button>
                              <button onClick={() => handleExport(v.platform_item_id, 'ai')}
                                className="text-[10px] px-1.5 py-0.5 rounded hover:bg-black/5 transition-colors text-[var(--color-ink-muted)]"
                                title="AI 整理导出">✨</button>
                              <button onClick={() => handleDelete(v.platform_item_id)}
                                className="text-[10px] px-1.5 py-0.5 rounded hover:bg-red-50 transition-colors text-[var(--color-ink-muted)] hover:text-red-500"
                                title="删除入库数据">🗑️</button>
                            </div>
                          )}
                          <span className={`text-[10px] ml-1 px-1.5 py-0.5 rounded-full flex-shrink-0 ${
                            v.status === 'done' ? 'bg-success-light text-success' :
                            v.status === 'pending' ? 'bg-amber-light text-amber' :
                            v.status === 'failed' ? 'bg-red-50 text-red-500' :
                            'bg-black/5 text-[var(--color-ink-muted)]'
                          }`}>
                            {v.status === 'done' ? '✓' : v.status === 'pending' ? '⏳' : v.status === 'failed' ? '✗' : v.status}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <hr className="border-[var(--color-border)]" />

        {/* Build Section */}
        <div className="flex flex-col gap-2">
          <h3 className="text-xs text-[var(--color-ink-soft)]">📥 {building ? '入库进度' : '入库状态'}</h3>

          {building ? (
            <>
              <p className="text-[11px] text-[var(--color-ink)] truncate">{buildMessage}</p>
              <div className="h-2 rounded-full bg-black/5 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-accent to-amber transition-all duration-700 ease-linear"
                  style={{ width: `${buildTotal ? (buildProgress / buildTotal) * 100 : 0}%` }}
                />
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-[var(--color-ink)] font-semibold">{buildProgress} / {buildTotal}</span>
                <span className="text-accent font-bold">{buildTotal ? Math.round((buildProgress / buildTotal) * 100) : 0}%</span>
              </div>
              <button disabled className="w-full py-3 rounded-full text-sm font-bold transition-all opacity-40 cursor-not-allowed"
                style={{ backgroundColor: 'rgba(0,0,0,0.06)', color: 'var(--color-ink-muted)' }}>
                ⏳ 入库中...
              </button>
            </>
          ) : (
            <>
              <p className="text-[11px] text-[var(--color-ink-muted)]">
                ✅ {doneCount} 已入库 · ⏳ {pendingCount} 待入库{failedCount > 0 ? ` · ❌ ${failedCount} 失败` : ''}{isStuck ? ' · ⚠️ 卡住' : ''} · 📊 {totalCount} 总计
              </p>
              <div className="h-1.5 rounded-full bg-black/5">
                <div className="h-full rounded-full bg-gradient-to-r from-accent to-amber transition-all duration-500" style={{ width: `${totalCount ? (doneCount / totalCount) * 100 : 0}%` }} />
              </div>
              {isStuck && (
                <button
                  onClick={async () => {
                    try { await api.resetFailedVideos(); fetchStats(); }
                    catch (e: any) { alert('重置失败: ' + e.message); }
                  }}
                  className="w-full py-2 rounded-full text-xs text-accent border border-accent/30 hover:bg-accent-light transition-colors"
                >
                  🔄 重置失败/卡住的视频
                </button>
              )}
              <button
                onClick={() => setShowBuildConfirm(true)}
                disabled={pendingCount === 0}
                className="w-full py-3 rounded-full bg-gradient-to-r from-accent to-accent-hover text-white text-sm font-bold shadow-md shadow-accent/20 hover:shadow-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              >
                🚀 一键入库 ({pendingCount})
              </button>
            </>
          )}
        </div>

        {/* History */}
        {sessions.length > 0 && (
          <>
            <hr className="border-[var(--color-border)]" />
            <div className="flex flex-col gap-1.5">
              <h3 className="text-xs text-[var(--color-ink-soft)]">💬 历史对话</h3>
              {sessions.slice(0, 8).map(s => (
                <div key={s.id} className="flex items-center justify-between px-2 py-1.5 rounded-lg text-xs hover:bg-black/3 cursor-pointer">
                  <span className="truncate flex-1 text-[var(--color-ink)]">{s.title}</span>
                  <span className="text-[var(--color-ink-muted)] ml-2 flex-shrink-0">{s.message_count}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {showBuildConfirm && (
        <BuildConfirmModal
          pendingCount={pendingCount}
          onClose={() => setShowBuildConfirm(false)}
          onConfirm={(selectedIds) => {
            setShowBuildConfirm(false);
            handleBuild(selectedIds);
          }}
        />
      )}
    </div>
  );
}
