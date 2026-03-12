import { type ReactNode, useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { Briefcase, FileText, Link as LinkIcon, Loader2, Pencil, Save, Sparkles, Trash2, UserRound } from 'lucide-react';
import { clearProfile, getProfile, parseResume, StructuredProfile, updateProfile } from '../lib/api';
import { useAuth } from '../lib/AuthContext';

interface ProfilePageProps {
  onProfileUpdated?: () => Promise<void> | void;
}

interface ProfileFormState {
  linkedin_url: string;
  experience_years: string;
  skills_text: string;
  tools_text: string;
  certifications_text: string;
  education_text: string;
  resume_text: string;
}

const EMPTY_FORM: ProfileFormState = {
  linkedin_url: '',
  experience_years: '',
  skills_text: '',
  tools_text: '',
  certifications_text: '',
  education_text: '',
  resume_text: '',
};

function formatEducationItem(item: string | Record<string, unknown>) {
  if (typeof item === 'string') return item;
  const institution = typeof item.institution === 'string' ? item.institution : '';
  const degree = typeof item.degree === 'string' ? item.degree : '';
  const field = typeof item.field === 'string' ? item.field : '';
  const year = typeof item.year === 'string' || typeof item.year === 'number' ? String(item.year) : '';
  return [degree, field, institution, year].filter(Boolean).join(' — ');
}

function splitList(text: string) {
  return text
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function mapProfileToForm(profile: StructuredProfile | null): ProfileFormState {
  if (!profile) return EMPTY_FORM;
  return {
    linkedin_url: profile.linkedin_url || '',
    experience_years: profile.experience_years != null ? String(profile.experience_years) : '',
    skills_text: (profile.skills || []).join('\n'),
    tools_text: (profile.tools || []).join('\n'),
    certifications_text: (profile.certifications || []).join('\n'),
    education_text: (profile.education || []).map(formatEducationItem).join('\n'),
    resume_text: profile.resume_text || '',
  };
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-slate-200/70 bg-white p-5 shadow-sm">
      <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-400 mb-4">{title}</h2>
      {children}
    </section>
  );
}

export function ProfilePage({ onProfileUpdated }: ProfilePageProps) {
  const { user, refreshUser } = useAuth();
  const [profile, setProfile] = useState<StructuredProfile | null>(null);
  const [form, setForm] = useState<ProfileFormState>(EMPTY_FORM);
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const loadProfile = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const data = await getProfile();
      setProfile(data);
      setForm(mapProfileToForm(data));
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to load profile.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadProfile();
  }, []);

  const hasStructuredProfile = useMemo(() => {
    return Boolean(
      form.linkedin_url ||
      form.experience_years ||
      form.skills_text ||
      form.tools_text ||
      form.certifications_text ||
      form.education_text ||
      form.resume_text
    );
  }, [form]);

  const handleSave = async () => {
    setSaving(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      const data = await updateProfile({
        linkedin_url: form.linkedin_url || null,
        experience_years: form.experience_years ? Number(form.experience_years) : null,
        skills: splitList(form.skills_text),
        tools: splitList(form.tools_text),
        certifications: splitList(form.certifications_text),
        education: splitList(form.education_text),
        resume_text: form.resume_text || null,
      });
      setProfile(data);
      setForm(mapProfileToForm(data));
      setEditing(false);
      setStatusMessage('Profile saved.');
      await Promise.all([refreshUser(), Promise.resolve(onProfileUpdated?.())]);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to save profile.');
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async () => {
    const confirmed = window.confirm('Clear all saved profile fields? This will remove your stored resume text and parsed profile data.');
    if (!confirmed) return;

    setSaving(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      await clearProfile();
      setProfile(null);
      setForm(EMPTY_FORM);
      setEditing(false);
      setStatusMessage('Profile cleared.');
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to clear profile.');
    } finally {
      setSaving(false);
    }
  };

  const handleParseResume = async () => {
    if (!form.resume_text.trim()) {
      setErrorMessage('Paste resume text before parsing.');
      return;
    }
    setParsing(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      const parsed = await parseResume(form.resume_text);
      setProfile(parsed);
      setForm(mapProfileToForm(parsed));
      setStatusMessage('Resume parsed and profile updated.');
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to parse resume.');
    } finally {
      setParsing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  const activeProfile = profile ? mapProfileToForm(profile) : form;
  const educationItems = splitList(activeProfile.education_text);
  const skillItems = splitList(activeProfile.skills_text);
  const toolItems = splitList(activeProfile.tools_text);
  const certificationItems = splitList(activeProfile.certifications_text);

  return (
    <div className="flex-1 overflow-auto p-8">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-3xl tracking-tight font-serif font-bold text-slate-900">Profile</h1>
            <p className="mt-1 text-slate-500 font-serif italic">
              Keep your search profile sharp so AppTrail can match jobs and personalize outreach.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {!editing ? (
              <button
                onClick={() => setEditing(true)}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
              >
                <Pencil className="w-4 h-4" />
                Edit Profile
              </button>
            ) : (
              <>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-800 disabled:opacity-60"
                >
                  {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  Save
                </button>
                <button
                  onClick={handleClear}
                  disabled={saving}
                  className="inline-flex items-center gap-2 rounded-xl border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-700 shadow-sm hover:bg-red-50 disabled:opacity-60"
                >
                  <Trash2 className="w-4 h-4" />
                  Clear
                </button>
              </>
            )}
          </div>
        </div>

        {(errorMessage || statusMessage) && (
          <div className={`rounded-2xl border px-4 py-3 text-sm ${
            errorMessage ? 'border-red-200 bg-red-50 text-red-800' : 'border-emerald-200 bg-emerald-50 text-emerald-800'
          }`}>
            {errorMessage || statusMessage}
          </div>
        )}

        <Section title="Identity">
          <div className="flex items-center gap-4">
            {user?.picture ? (
              <img src={user.picture} alt={user.name || 'User'} className="h-14 w-14 rounded-2xl border border-slate-200 object-cover" referrerPolicy="no-referrer" />
            ) : (
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-200 text-slate-600">
                <UserRound className="w-6 h-6" />
              </div>
            )}
            <div className="min-w-0">
              <div className="text-lg font-semibold text-slate-900">{user?.name || 'User'}</div>
              <div className="text-sm text-slate-500">{user?.email}</div>
            </div>
          </div>

          {editing ? (
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <label className="space-y-2">
                <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">LinkedIn URL</span>
                <input
                  value={form.linkedin_url}
                  onChange={(event) => setForm((prev) => ({ ...prev, linkedin_url: event.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none focus:border-slate-300 focus:ring-2 focus:ring-slate-200"
                  placeholder="https://linkedin.com/in/your-profile"
                />
              </label>
              <label className="space-y-2">
                <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">Years of Experience</span>
                <input
                  type="number"
                  min="0"
                  value={form.experience_years}
                  onChange={(event) => setForm((prev) => ({ ...prev, experience_years: event.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none focus:border-slate-300 focus:ring-2 focus:ring-slate-200"
                  placeholder="5"
                />
              </label>
            </div>
          ) : (
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              {activeProfile.linkedin_url && (
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">LinkedIn</div>
                  <a href={activeProfile.linkedin_url} target="_blank" rel="noreferrer noopener" className="mt-1 inline-flex items-center gap-2 text-sm font-medium text-slate-800 hover:text-slate-900">
                    <LinkIcon className="w-4 h-4" />
                    {activeProfile.linkedin_url}
                  </a>
                </div>
              )}
              {activeProfile.experience_years && (
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Experience</div>
                  <div className="mt-1 text-sm font-medium text-slate-800">{activeProfile.experience_years} years</div>
                </div>
              )}
            </div>
          )}
        </Section>

        {editing && (
          <Section title="Resume">
            <div className="space-y-3">
              <p className="text-sm text-slate-500">
                Paste resume text here, then parse it to auto-fill your profile sections.
              </p>
              <textarea
                value={form.resume_text}
                onChange={(event) => setForm((prev) => ({ ...prev, resume_text: event.target.value }))}
                className="min-h-[220px] w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none focus:border-slate-300 focus:ring-2 focus:ring-slate-200"
                placeholder="Paste your resume text here..."
              />
              <button
                onClick={handleParseResume}
                disabled={parsing}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-60"
              >
                {parsing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                Parse Resume Into Profile
              </button>
            </div>
          </Section>
        )}

        {!editing && !hasStructuredProfile && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-3xl border border-dashed border-slate-200 bg-white p-10 text-center shadow-sm"
          >
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
              <Briefcase className="w-6 h-6" />
            </div>
            <h2 className="text-lg font-semibold text-slate-900">Build your profile</h2>
            <p className="mt-2 text-sm text-slate-500 max-w-xl mx-auto">
              Add your resume text, skills, education, and certifications so AppTrail can improve job fit scoring and personalization.
            </p>
          </motion.div>
        )}

        {(editing || skillItems.length > 0) && (
          <Section title="Skills">
            {editing ? (
              <textarea
                value={form.skills_text}
                onChange={(event) => setForm((prev) => ({ ...prev, skills_text: event.target.value }))}
                className="min-h-[140px] w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none focus:border-slate-300 focus:ring-2 focus:ring-slate-200"
                placeholder="One skill per line"
              />
            ) : (
              <div className="flex flex-wrap gap-2">
                {skillItems.map((item) => (
                  <span key={item} className="rounded-full bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700">
                    {item}
                  </span>
                ))}
              </div>
            )}
          </Section>
        )}

        {(editing || toolItems.length > 0) && (
          <Section title="Tools">
            {editing ? (
              <textarea
                value={form.tools_text}
                onChange={(event) => setForm((prev) => ({ ...prev, tools_text: event.target.value }))}
                className="min-h-[120px] w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none focus:border-slate-300 focus:ring-2 focus:ring-slate-200"
                placeholder="One tool per line"
              />
            ) : (
              <div className="flex flex-wrap gap-2">
                {toolItems.map((item) => (
                  <span key={item} className="rounded-full bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-700">
                    {item}
                  </span>
                ))}
              </div>
            )}
          </Section>
        )}

        {(editing || educationItems.length > 0) && (
          <Section title="Education">
            {editing ? (
              <textarea
                value={form.education_text}
                onChange={(event) => setForm((prev) => ({ ...prev, education_text: event.target.value }))}
                className="min-h-[140px] w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none focus:border-slate-300 focus:ring-2 focus:ring-slate-200"
                placeholder="One education entry per line"
              />
            ) : (
              <div className="space-y-2">
                {educationItems.map((item) => (
                  <div key={item} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                    {item}
                  </div>
                ))}
              </div>
            )}
          </Section>
        )}

        {(editing || certificationItems.length > 0) && (
          <Section title="Certifications">
            {editing ? (
              <textarea
                value={form.certifications_text}
                onChange={(event) => setForm((prev) => ({ ...prev, certifications_text: event.target.value }))}
                className="min-h-[120px] w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none focus:border-slate-300 focus:ring-2 focus:ring-slate-200"
                placeholder="One certification per line"
              />
            ) : (
              <div className="space-y-2">
                {certificationItems.map((item) => (
                  <div key={item} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                    {item}
                  </div>
                ))}
              </div>
            )}
          </Section>
        )}

        {!editing && activeProfile.resume_text && (
          <Section title="Resume">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                <FileText className="w-4 h-4" />
                Resume text saved
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600 whitespace-pre-wrap line-clamp-6 [overflow-wrap:anywhere]">
                {activeProfile.resume_text}
              </p>
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}
