import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Building2, Mail, Users, Code, BarChart2, X, ExternalLink, Briefcase } from 'lucide-react';
import { apiFetch, authHeaders } from '../lib/api';

interface CompanyDetailProps {
  domain: string;
  onClose: () => void;
}

export function CompanyDetail({ domain, onClose }: CompanyDetailProps) {
  const [context, setContext] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadContext();
  }, [domain]);

  const loadContext = async () => {
    setLoading(true);
    try {
      const res = await apiFetch(`/api/companies/${encodeURIComponent(domain)}/context`, { headers: authHeaders() });
      if (res.ok) setContext(await res.json());
    } catch (err) {
      console.error('Failed to load company context:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/20 backdrop-blur-sm"
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        onClick={e => e.stopPropagation()}
        className="bg-white w-full max-w-2xl max-h-[85vh] flex flex-col rounded-3xl shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="p-6 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-4">
            {context?.identity?.logo_url ? (
              <img src={context.identity.logo_url} alt="" className="w-12 h-12 rounded-xl border border-slate-200" />
            ) : (
              <div className="w-12 h-12 rounded-xl bg-slate-200 flex items-center justify-center">
                <Building2 className="w-6 h-6 text-slate-500" />
              </div>
            )}
            <div>
              <h2 className="text-xl font-serif font-bold text-slate-900">{context?.identity?.name || domain}</h2>
              <p className="text-sm text-slate-500">{domain}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-200 rounded-lg">
            <X className="w-5 h-5 text-slate-500" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {loading ? (
            <div className="text-center py-12">
              <div className="w-8 h-8 border-2 rounded-full border-slate-300 border-t-slate-600 animate-spin mx-auto mb-4" />
              <p className="text-slate-400 font-serif">Loading company intelligence...</p>
            </div>
          ) : !context?.found ? (
            <p className="text-center text-slate-400 py-12">No data found for this company.</p>
          ) : (
            <>
              {/* Summary Stats */}
              <div className="grid grid-cols-4 gap-3">
                {[
                  { label: 'Applications', value: context.summary.total_applications, icon: Briefcase },
                  { label: 'Contacts', value: context.summary.total_contacts, icon: Users },
                  { label: 'Emails', value: context.summary.total_emails, icon: Mail },
                  { label: 'Technologies', value: context.summary.tech_count, icon: Code },
                ].map(stat => (
                  <div key={stat.label} className="p-3 bg-slate-50 rounded-xl text-center">
                    <stat.icon className="w-4 h-4 text-slate-400 mx-auto mb-1" />
                    <p className="text-lg font-bold text-slate-900">{stat.value}</p>
                    <p className="text-[10px] text-slate-400">{stat.label}</p>
                  </div>
                ))}
              </div>

              {/* ATS & Response Stats */}
              {(context.ats_profile || Object.keys(context.response_stats).length > 0) && (
                <div className="p-4 bg-indigo-50/50 rounded-2xl border border-indigo-100">
                  <h3 className="text-sm font-bold text-slate-900 mb-2 flex items-center gap-2">
                    <BarChart2 className="w-4 h-4" /> Intelligence
                  </h3>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    {context.ats_profile && (
                      <div>
                        <p className="text-xs text-slate-500">ATS Platform</p>
                        <p className="font-medium text-slate-900">{context.ats_profile.platform}</p>
                      </div>
                    )}
                    {context.response_stats.avg_response_days !== undefined && (
                      <div>
                        <p className="text-xs text-slate-500">Avg Response Time</p>
                        <p className="font-medium text-slate-900">{context.response_stats.avg_response_days} days</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Tech Stack */}
              {context.tech_stack.length > 0 && (
                <div>
                  <h3 className="text-sm font-bold text-slate-900 mb-2">Tech Stack</h3>
                  <div className="flex flex-wrap gap-1.5">
                    {context.tech_stack.map((t: any) => (
                      <span key={t.name} className="px-2 py-0.5 text-xs font-medium bg-slate-100 text-slate-600 rounded-full">
                        {t.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Applications */}
              {context.applications.length > 0 && (
                <div>
                  <h3 className="text-sm font-bold text-slate-900 mb-2">Applications</h3>
                  <div className="space-y-2">
                    {context.applications.map((app: any) => (
                      <div key={app.id} className="p-3 bg-slate-50 rounded-xl flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-slate-900">{app.role_title}</p>
                          <p className="text-xs text-slate-400">{app.applied_at ? new Date(app.applied_at).toLocaleDateString() : ''}</p>
                        </div>
                        <span className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-slate-200 text-slate-600">{app.status}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Warm Connections */}
              {context.warm_connections.length > 0 && (
                <div>
                  <h3 className="text-sm font-bold text-slate-900 mb-2">Warm Connections</h3>
                  <div className="space-y-2">
                    {context.warm_connections.map((w: any, i: number) => (
                      <div key={i} className="p-3 bg-emerald-50 rounded-xl">
                        <p className="text-sm font-medium text-slate-900">{w.contact_name || w.contact_email}</p>
                        <p className="text-xs text-slate-400">{w.email_count} emails</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}
