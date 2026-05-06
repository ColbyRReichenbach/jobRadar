import { motion } from 'motion/react';
import { useState } from 'react';
import { Logo } from './Logo';
import { useAuth } from '../lib/AuthContext';
import { LOCAL_DEV_AUTH_ENABLED } from '../lib/api';

export function LoginPage() {
  const { signIn, signInGoogle } = useAuth();
  const [localEmail, setLocalEmail] = useState('account1@apptrailtest.com');
  const [localName, setLocalName] = useState('Account 1');

  const handleLocalSignIn = () => {
    signIn({
      email: localEmail.trim() || undefined,
      name: localName.trim() || undefined,
    });
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F5F5F0] p-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-sm"
      >
        <div className="text-center mb-8">
          <Logo className="mx-auto mb-4 h-20 w-20" />
          <h1 className="text-3xl tracking-tight font-serif font-bold text-slate-900">
            Opportunity Radar
          </h1>
          <p className="mt-2 text-slate-500 font-serif italic">
            Turn job-search signals into your next move.
          </p>
        </div>

        <div className="bg-white rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-slate-100 p-8">
          {LOCAL_DEV_AUTH_ENABLED ? (
            <div className="space-y-3">
              <label className="block">
                <span className="block text-xs font-medium text-slate-500 mb-1">Local test user email</span>
                <input
                  value={localEmail}
                  onChange={(event) => setLocalEmail(event.target.value)}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
                  placeholder="account1@apptrailtest.com"
                />
              </label>
              <label className="block">
                <span className="block text-xs font-medium text-slate-500 mb-1">Display name</span>
                <input
                  value={localName}
                  onChange={(event) => setLocalName(event.target.value)}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
                  placeholder="Account 1"
                />
              </label>
              <button
                onClick={handleLocalSignIn}
                className="w-full flex items-center justify-center gap-3 py-3.5 bg-white border border-slate-200 rounded-xl font-medium text-slate-700 hover:bg-slate-50 transition-colors shadow-sm"
              >
                <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-slate-800 text-[10px] font-semibold text-white">L</span>
                Continue locally
              </button>
              <button
                onClick={signInGoogle}
                className="w-full flex items-center justify-center gap-3 py-3.5 bg-white border border-slate-200 rounded-xl font-medium text-slate-700 hover:bg-slate-50 transition-colors shadow-sm"
              >
                <GoogleIcon />
                Sign in with Google
              </button>
            </div>
          ) : (
            <button
              onClick={() => signIn()}
              className="w-full flex items-center justify-center gap-3 py-3.5 bg-white border border-slate-200 rounded-xl font-medium text-slate-700 hover:bg-slate-50 transition-colors shadow-sm"
            >
              <GoogleIcon />
              Sign in with Google
            </button>
          )}

          <p className="text-center text-xs text-slate-400 mt-6">
            {LOCAL_DEV_AUTH_ENABLED
              ? 'Use a different local email for each Gmail account, then connect Gmail inside the app.'
              : 'Sign in to sync your Gmail and track applications automatically.'}
          </p>
        </div>
      </motion.div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg className="w-5 h-5" viewBox="0 0 24 24">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  );
}
