import { useState, useEffect, useCallback } from 'react';
import LandingPage from './pages/LandingPage';
import Workspace from './pages/Workspace';
import LoginModal from './components/LoginModal';
import * as api from './api';

export default function App() {
  const requiresAccessToken = import.meta.env.VITE_REQUIRE_APP_TOKEN === 'true';
  const [unlocked, setUnlocked] = useState(
    () => !requiresAccessToken || Boolean(api.getAccessToken()),
  );
  const [accessToken, setAccessTokenInput] = useState('');
  const [accessError, setAccessError] = useState('');
  const [loggedIn, setLoggedIn] = useState(false);
  const [showLogin, setShowLogin] = useState(false);
  const [loginBusy, setLoginBusy] = useState(false);

  // Poll login status
  useEffect(() => {
    if (!unlocked) return;
    const check = async () => {
      try {
        const s = await api.loginStatus();
        setLoggedIn(s.status === 'logged_in');
      } catch { /* backend not ready */ }
    };
    check();
    const timer = setInterval(check, loggedIn ? 30000 : 5000);
    return () => clearInterval(timer);
  }, [loggedIn, unlocked]);

  const unlock = async () => {
    setAccessError('');
    api.setAccessToken(accessToken);
    try {
      await api.loginStatus();
      setUnlocked(true);
    } catch {
      api.setAccessToken('');
      setAccessError('访问口令不正确，或后端还没有启动');
    }
  };

  if (!unlocked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg)] px-6">
        <div className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-xl text-center">
          <div className="w-12 h-12 mx-auto mb-5 rounded-xl flex items-center justify-center bg-gradient-to-br from-accent to-amber">
            <span className="font-display text-white text-2xl font-bold">D</span>
          </div>
          <h1 className="font-display text-2xl text-[var(--color-ink)]">DouyinMind</h1>
          <p className="mt-2 mb-6 text-sm text-[var(--color-ink-soft)]">这是你的专属知识库，请输入访问口令。</p>
          <input
            type="password"
            value={accessToken}
            onChange={e => setAccessTokenInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') unlock(); }}
            placeholder="访问口令"
            className="w-full rounded-xl border border-[var(--color-border)] px-4 py-3 text-sm outline-none focus:border-accent"
          />
          {accessError && <p className="mt-3 text-xs text-red-500">{accessError}</p>}
          <button onClick={unlock} className="mt-4 w-full rounded-xl bg-accent py-3 text-sm font-bold text-white hover:bg-accent-hover transition-colors">进入知识库</button>
        </div>
      </div>
    );
  }

  const handleLogin = useCallback(async () => {
    setLoginBusy(true);
    try {
      const r = await api.loginStart();
      if (r.success) {
        setShowLogin(true);
      }
    } catch (e) {
      console.error(e);
    }
    setLoginBusy(false);
  }, []);

  const handleLoginSuccess = useCallback(() => {
    setShowLogin(false);
    setLoggedIn(true);
  }, []);

  const handleLogout = useCallback(async () => {
    try { await api.logout(); } catch {}
    setLoggedIn(false);
  }, []);

  if (!loggedIn) {
    return (
      <>
        <LandingPage onStartLogin={handleLogin} busy={loginBusy} />
        {showLogin && (
          <LoginModal
            onClose={() => setShowLogin(false)}
            onSuccess={handleLoginSuccess}
          />
        )}
      </>
    );
  }

  return <Workspace onLogout={handleLogout} />;
}
