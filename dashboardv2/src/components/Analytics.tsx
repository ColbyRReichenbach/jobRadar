import { useState, useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, AreaChart, Area } from 'recharts';
import { Job } from '../types';
import { motion } from 'motion/react';
import { format, subDays, startOfWeek, eachDayOfInterval, isSameDay, isAfter } from 'date-fns';
import { Calendar } from 'lucide-react';

interface AnalyticsProps {
  jobs: Job[];
}

export function Analytics({ jobs }: AnalyticsProps) {
  const [timeRange, setTimeRange] = useState('30d');

  const filteredJobs = useMemo(() => {
    if (timeRange === 'all') return jobs;
    const days = parseInt(timeRange);
    const cutoff = subDays(new Date(), days);
    return jobs.filter(job => isAfter(new Date(job.dateAdded), cutoff));
  }, [jobs, timeRange]);

  const pipelineData = [
    { name: 'Saved', count: filteredJobs.filter(j => j.status === 'saved').length },
    { name: 'Applied', count: filteredJobs.filter(j => j.status === 'applied').length },
    { name: 'Interviewing', count: filteredJobs.filter(j => j.status === 'interviewing').length },
    { name: 'Offer', count: filteredJobs.filter(j => j.status === 'offer').length },
    { name: 'Rejected', count: filteredJobs.filter(j => j.status === 'rejected').length },
  ];

  const roleGroups = filteredJobs.reduce((acc, job) => {
    let group = 'Other';
    const role = job.role.toLowerCase();
    if (role.includes('engineer') || role.includes('developer')) group = 'Engineering';
    else if (role.includes('design')) group = 'Design';
    else if (role.includes('product')) group = 'Product';
    
    acc[group] = (acc[group] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const pieData = Object.entries(roleGroups).map(([name, value]) => ({ name, value }));
  const COLORS = ['#818cf8', '#34d399', '#f472b6', '#fbbf24'];

  // Calculate activity over the selected time range
  const today = new Date();
  const daysToSubtract = timeRange === 'all' ? 90 : parseInt(timeRange);
  const intervalStart = subDays(today, daysToSubtract - 1);
  const dateInterval = eachDayOfInterval({ start: intervalStart, end: today });
  
  const activityData = dateInterval.map(day => {
    const appsOnDay = jobs.filter(j => isSameDay(new Date(j.dateAdded), day) && j.status !== 'saved').length;
    return {
      date: format(day, 'MMM d'),
      applications: appsOnDay
    };
  });

  // Calculate top companies applied to
  const companyCounts = filteredJobs.reduce((acc, job) => {
    if (job.status !== 'saved') {
      acc[job.company] = (acc[job.company] || 0) + 1;
    }
    return acc;
  }, {} as Record<string, number>);

  const topCompaniesData = Object.entries(companyCounts)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => Number(b.count) - Number(a.count))
    .slice(0, 5); // Top 5 companies

  // Calculate conversion rates
  const totalApplied = filteredJobs.filter(j => j.status !== 'saved').length;
  const totalInterviews = filteredJobs.filter(j => j.status === 'interviewing' || j.status === 'offer' || j.status === 'rejected').length; // Assuming rejected might have had an interview, simplified for now
  const totalOffers = filteredJobs.filter(j => j.status === 'offer').length;

  const conversionRate = totalApplied > 0 ? ((totalInterviews / totalApplied) * 100).toFixed(1) : '0';
  const offerRate = totalInterviews > 0 ? ((totalOffers / totalInterviews) * 100).toFixed(1) : '0';
  const hasAnalyticsData = filteredJobs.length > 0;

  const timeRangeText = timeRange === 'all' ? 'all time' : `the last ${timeRange.replace('d', ' days')}`;

  return (
    <div className="flex-1 h-full overflow-y-auto p-4 md:p-8 bg-[#F5F5F0]">
      <div className="w-full">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-3xl tracking-tight font-serif font-bold text-slate-900">
              Analytics
            </h1>
            <p className="mt-1 text-slate-500 font-serif italic">
              Visualize your job search progress and uncover insights.
            </p>
          </div>
          <div className="flex items-center gap-2 bg-white px-3 py-1.5 rounded-xl border border-slate-200 shadow-sm shrink-0">
            <Calendar className="w-4 h-4 text-slate-400" />
            <select 
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              className="bg-transparent border-none text-sm font-medium text-slate-700 outline-none cursor-pointer"
            >
              <option value="7d">Last 7 Days</option>
              <option value="14d">Last 14 Days</option>
              <option value="30d">Last 30 Days</option>
              <option value="90d">Last 90 Days</option>
              <option value="all">All Time</option>
            </select>
          </div>
        </div>

        {/* Top Metrics */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
            <h3 className="text-sm font-medium text-slate-500 mb-1">Total Applications</h3>
            <p className="text-3xl font-serif font-bold text-slate-900">{totalApplied}</p>
          </motion.div>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
            <h3 className="text-sm font-medium text-slate-500 mb-1">Active Interviews</h3>
            <p className="text-3xl font-serif font-bold text-indigo-600">{pipelineData[2].count}</p>
          </motion.div>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
            <h3 className="text-sm font-medium text-slate-500 mb-1">Interview Rate</h3>
            <p className="text-3xl font-serif font-bold text-blue-600">{conversionRate}%</p>
          </motion.div>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
            <h3 className="text-sm font-medium text-slate-500 mb-1">Offers Received</h3>
            <p className="text-3xl font-serif font-bold text-emerald-600">{totalOffers}</p>
          </motion.div>
        </div>

        {!hasAnalyticsData && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white rounded-3xl border border-slate-100 shadow-sm p-10 text-center"
          >
            <h2 className="text-2xl font-serif font-bold text-slate-900">No analytics yet</h2>
            <p className="mt-3 text-slate-500">
              Add jobs to your pipeline and move them through statuses to unlock charts, conversion rates, and source breakdowns.
            </p>
          </motion.div>
        )}

        {/* Main Charts Grid */}
        {hasAnalyticsData && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          
          {/* Activity Timeline - Spans full width */}
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.4 }} className="lg:col-span-3 bg-white p-6 rounded-3xl shadow-sm border border-slate-100 h-[400px] flex flex-col">
            <div className="mb-6">
              <h3 className="text-xl font-serif font-bold text-slate-900">Application Activity</h3>
              <p className="text-sm text-slate-500">Your momentum over {timeRangeText}</p>
            </div>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={activityData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorApps" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#818cf8" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#818cf8" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                  <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} allowDecimals={false} />
                  <Tooltip 
                    cursor={{ stroke: '#cbd5e1', strokeWidth: 1, strokeDasharray: '4 4' }}
                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 20px rgba(0,0,0,0.08)' }}
                  />
                  <Area type="monotone" dataKey="applications" stroke="#818cf8" strokeWidth={3} fillOpacity={1} fill="url(#colorApps)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </motion.div>

          {/* Pipeline Funnel - Spans 2 columns */}
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.5 }} className="lg:col-span-2 bg-white p-6 rounded-3xl shadow-sm border border-slate-100 h-[400px] flex flex-col">
            <div className="mb-6">
              <h3 className="text-xl font-serif font-bold text-slate-900">Pipeline Funnel</h3>
              <p className="text-sm text-slate-500">Current status of all tracked jobs</p>
            </div>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={pipelineData} layout="vertical" margin={{ top: 0, right: 20, left: 80, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                  <XAxis type="number" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
                  <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: '#475569', fontSize: 13, fontWeight: 500 }} width={80} />
                  <Tooltip 
                    cursor={{ fill: '#f8fafc' }}
                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 20px rgba(0,0,0,0.08)' }}
                  />
                  <Bar dataKey="count" fill="#34d399" radius={[0, 6, 6, 0]} barSize={32}>
                    {pipelineData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={
                        entry.name === 'Offer' ? '#10b981' : 
                        entry.name === 'Interviewing' ? '#6366f1' : 
                        entry.name === 'Rejected' ? '#ef4444' : '#94a3b8'
                      } />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </motion.div>

          {/* Roles Breakdown - Spans 1 column */}
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.7 }} className="lg:col-span-1 bg-white p-6 rounded-3xl shadow-sm border border-slate-100 h-[400px] flex flex-col">
            <div className="mb-2">
              <h3 className="text-xl font-serif font-bold text-slate-900">Roles Breakdown</h3>
              <p className="text-sm text-slate-500">Distribution of applied roles</p>
            </div>
            <div className="flex-1 min-h-0 relative">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip 
                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 20px rgba(0,0,0,0.08)' }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute inset-x-0 bottom-0 flex justify-center gap-4 flex-wrap pb-2">
                {pieData.map((entry, index) => (
                  <div key={entry.name} className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                    <span className="text-xs text-slate-600 font-medium">{entry.name}</span>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>

          {/* Top Companies - Spans 2 columns */}
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.6 }} className="lg:col-span-2 bg-white p-6 rounded-3xl shadow-sm border border-slate-100 h-[350px] flex flex-col">
            <div className="mb-6">
              <h3 className="text-xl font-serif font-bold text-slate-900">Top Companies</h3>
              <p className="text-sm text-slate-500">Where you've applied the most</p>
            </div>
            <div className="flex-1 min-h-0">
              {topCompaniesData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={topCompaniesData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} allowDecimals={false} />
                    <Tooltip 
                      cursor={{ fill: '#f8fafc' }}
                      contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 20px rgba(0,0,0,0.08)' }}
                    />
                    <Bar dataKey="count" fill="#fbbf24" radius={[6, 6, 0, 0]} barSize={40} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-slate-400 text-sm">
                  Not enough data yet.
                </div>
              )}
            </div>
          </motion.div>

          {/* Application Sources - Spans 1 column */}
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.8 }} className="lg:col-span-1 bg-white p-6 rounded-3xl shadow-sm border border-slate-100 h-[350px] flex flex-col">
            <div className="mb-6">
              <h3 className="text-xl font-serif font-bold text-slate-900">Sources</h3>
              <p className="text-sm text-slate-500">Where you find your jobs</p>
            </div>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={[
                  { name: 'LinkedIn', count: filteredJobs.filter(j => j.source === 'linkedin').length },
                  { name: 'Company Site', count: filteredJobs.filter(j => j.source === 'company_site').length },
                  { name: 'Indeed', count: filteredJobs.filter(j => j.source === 'indeed').length },
                  { name: 'Glassdoor', count: filteredJobs.filter(j => j.source === 'glassdoor').length },
                ].sort((a, b) => b.count - a.count)} layout="vertical" margin={{ top: 0, right: 20, left: 60, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                  <XAxis type="number" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
                  <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: '#475569', fontSize: 12, fontWeight: 500 }} width={80} />
                  <Tooltip 
                    cursor={{ fill: '#f8fafc' }}
                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 20px rgba(0,0,0,0.08)' }}
                  />
                  <Bar dataKey="count" fill="#818cf8" radius={[0, 6, 6, 0]} barSize={24} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </motion.div>

        </div>
        )}
      </div>
    </div>
  );
}
