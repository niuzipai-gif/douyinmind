import { useState, useEffect, useCallback } from 'react';
import * as api from '../api';

interface Props { onClose: () => void; onSuccess: () => void; }

export default function LoginModal({ onClose, onSuccess }: Props) {
  const [status, setStatus] = useState('pending');
  const [message, setMessage] = useState('正在生成二维码，请稍候');
  const [qrUrl, setQrUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let currentQrUrl: string | null = null;
    let successTimer: number | undefined;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const s = await api.loginStatus();
        if (!active) return;
        setMessage(s.message);
        if (s.status === 'logged_in') {
          setStatus('success');
          if (timer) window.clearInterval(timer);
          successTimer = window.setTimeout(onSuccess, 800);
        } else if (s.status === 'failed') {
          setStatus('failed');
          if (timer) window.clearInterval(timer);
        } else {
          try {
            const blob = await api.loginQr();
            const nextQrUrl = URL.createObjectURL(blob);
            if (!active) {
              URL.revokeObjectURL(nextQrUrl);
              return;
            }
            if (currentQrUrl) URL.revokeObjectURL(currentQrUrl);
            currentQrUrl = nextQrUrl;
            setQrUrl(nextQrUrl);
          } catch { /* QR 尚未生成，继续轮询 */ }
        }
      } catch { /* ignore */ }
    };

    void poll();
    timer = window.setInterval(poll, 1500);
    return () => {
      active = false;
      if (timer) window.clearInterval(timer);
      if (successTimer) window.clearTimeout(successTimer);
      if (currentQrUrl) URL.revokeObjectURL(currentQrUrl);
    };
  }, [onSuccess]);

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-[var(--color-panel)] rounded-2xl p-8 w-[400px] flex flex-col items-center gap-5 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <h2 className="font-display text-xl text-[var(--color-ink)]">
          {status === 'success' ? '✅ 登录成功' : status === 'failed' ? '❌ 登录失败' : '🔐 登录抖音'}
        </h2>

        <div className="w-48 h-48 rounded-xl bg-black/3 flex items-center justify-center">
          {status === 'pending' && qrUrl ? (
            <img src={qrUrl} alt="抖音登录二维码" className="w-full h-full rounded-xl object-contain" />
          ) : (
            <span className="text-5xl">{status === 'pending' ? '⏳' : status === 'success' ? '✅' : '❌'}</span>
          )}
        </div>

        <p className="text-sm text-[var(--color-ink-soft)] text-center">{message}</p>

        <div className="w-full flex flex-col gap-2 text-xs text-[var(--color-ink-soft)]">
          <div className="flex gap-2"><span className="text-accent font-bold">1.</span>用抖音 App 扫描上方二维码</div>
          <div className="flex gap-2"><span className="text-accent font-bold">2.</span>在手机上确认登录</div>
          <div className="flex gap-2"><span className="text-accent font-bold">3.</span>登录成功后自动同步收藏夹</div>
        </div>

        <button onClick={onClose} className="text-sm text-[var(--color-ink-muted)] hover:text-[var(--color-ink)] transition-colors">
          取消
        </button>
      </div>
    </div>
  );
}
