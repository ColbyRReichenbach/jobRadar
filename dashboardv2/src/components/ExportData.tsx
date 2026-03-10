import { Download, FileSpreadsheet, CheckCircle2 } from 'lucide-react';
import { motion } from 'motion/react';
import { useState } from 'react';
import { exportCsv } from '../lib/api';

export function ExportData() {
  const [isExporting, setIsExporting] = useState(false);
  const [exported, setExported] = useState(false);

  const handleExport = async () => {
    setIsExporting(true);
    try {
      await exportCsv();
      setExported(true);
      setTimeout(() => setExported(false), 3000);
    } catch (err) {
      console.error('Export failed:', err);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="flex-1 h-full overflow-y-auto p-4 md:p-8 flex items-center justify-center bg-[#F5F5F0]">
      <motion.div 
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="p-8 max-w-md w-full text-center transition-all bg-white rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-slate-100"
      >
        <div className="w-16 h-16 flex items-center justify-center mx-auto mb-6 bg-slate-50 rounded-2xl">
          <FileSpreadsheet className="w-8 h-8 text-slate-700" />
        </div>
        <h1 className="text-3xl tracking-tight font-serif font-bold text-slate-900 mb-2">Export Your Data</h1>
        <p className="mb-8 text-slate-500 font-serif italic">
          Download a complete CSV of your job pipeline, contacts, and AI-classified email history.
        </p>

        <button 
          onClick={handleExport}
          disabled={isExporting || exported}
          className="w-full flex items-center justify-center gap-2 py-3.5 transition-all bg-slate-800 hover:bg-slate-900 text-white rounded-xl font-medium shadow-sm disabled:bg-slate-200 disabled:shadow-[0px_0px_0px_0px_rgba(0,0,0,1)] disabled:translate-y-1"
        >
          {isExporting ? (
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
              className="w-5 h-5 border-2 rounded-full border-slate-400/30 border-t-slate-400"
            />
          ) : exported ? (
            <>
              <CheckCircle2 className="w-5 h-5" />
              Exported Successfully
            </>
          ) : (
            <>
              <Download className="w-5 h-5" />
              Download CSV
            </>
          )}
        </button>
      </motion.div>
    </div>
  );
}
