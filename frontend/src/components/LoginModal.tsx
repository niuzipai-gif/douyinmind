import { useState, useEffect } from 'react';
import * as api from '../api';

interface Props { onClose: () => void; onSuccess: () => void; }

export default function LoginModal({ onClose, onSuccess }: Props) {
  const [status, setStatus] = useState('pending');
  const [message, setMessage] = useState('等待本机登录助手连接...');

  useEffect(() => {
    let active = true;
    let successTimer: number | undefined;

    const poll = async () => {
      try {
        const result = await api.loginStatus();
        if (!active) return;
        if (result.status === 'logged_in') {
          setStatus('success');
          setMessage(result.message || '本机登录成功，正在进入知识库');
          successTimer = window.setTimeout(onSuccess, 800);
        } else if (result.status === 'failed') {
          setStatus('failed');
          setMessage(result.message || '本机登录失败，请重试');
        } else {
          setStatus('pending');
          setMessage('等待本机登录助手完成扫码；如遇验证码，请在本机浏览器完成');
        }
      } catch {
        if (active) setMessage('云端暂时无法连接，请确认网络正常');
      }
    };

    void poll();
    const timer = window.setInterval(poll, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
      if (successTimer) window.clearTimeout(successTimer);
    };
  }, [onSuccess]);

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-[var(--color-panel)] rounded-2xl p-8 w-full max-w-[440px] mx-5 flex flex-col items-center gap-5 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <h2 className="font-display text-xl text-[var(--color-ink)]">
          {status === 'success' ? '✅ 登录成功' : status === 'failed' ? '❌ 登录失败' : '🖥️ 本机扫码登录'}
        </h2>

        <div className="w-full rounded-xl bg-black/3 px-5 py-6 text-center">
          <div className="text-5xl mb-4">{status === 'success' ? '✅' : status === 'failed' ? '⚠️' : '🔐'}</div>
          <p className="text-sm text-[var(--color-ink-soft)]">{message}</p>
        </div>

        <div className="w-full flex flex-col gap-2 text-xs text-[var(--color-ink-soft)]">
          <div className="flex gap-2"><span className="text-accent font-bold">1.</span>双击仓库里的 <code className="text-accent">backend\start_local_login.cmd</code></div>
          <div className="flex gap-2"><span className="text-accent font-bold">2.</span>在本机浏览器扫码并完成抖音验证</div>
          <div className="flex gap-2"><span className="text-accent font-bold">3.</span>登录态上传完成后，此页面自动进入知识库</div>
        </div>

        <button onClick={onClose} className="text-sm text-[var(--color-ink-muted)] hover:text-[var(--color-ink)] transition-colors">
          取消
        </button>
      </div>
    </div>
  );
}
