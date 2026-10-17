import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col selection:bg-indigo-500 selection:text-white">
      {/* Navigation */}
      <header className="border-b border-slate-800/80 backdrop-blur-md sticky top-0 z-50 bg-slate-950/70">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-500 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20 font-bold text-lg text-white">
              AI
            </div>
            <span className="font-semibold text-lg tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
              InterviewPrep AI
            </span>
          </div>

          <div className="flex items-center gap-4">
            <Link
              href="/login"
              className="text-sm font-medium text-slate-300 hover:text-white transition px-3 py-2 rounded-lg hover:bg-slate-800/50"
            >
              Sign In
            </Link>
            <Link
              href="/register"
              className="text-sm font-semibold text-white bg-gradient-to-r from-indigo-500 to-violet-600 hover:from-indigo-400 hover:to-violet-500 px-4 py-2 rounded-lg shadow-md shadow-indigo-500/20 transition-all hover:shadow-indigo-500/30"
            >
              Get Started Free
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <main className="flex-1 max-w-7xl mx-auto px-6 py-16 flex flex-col items-center justify-center text-center">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 text-xs font-medium text-indigo-300 mb-8 animate-pulse">
          <span className="w-2 h-2 rounded-full bg-indigo-400"></span>
          Intelligent Mock Interviews with Instant Feedback
        </div>

        <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight max-w-4xl leading-[1.15] text-balance">
          Master Your Next Tech Interview with{" "}
          <span className="bg-gradient-to-r from-indigo-400 via-purple-300 to-pink-400 bg-clip-text text-transparent">
            AI-Powered Simulation
          </span>
        </h1>

        <p className="mt-6 text-lg sm:text-xl text-slate-400 max-w-2xl leading-relaxed">
          Practice role-specific technical questions, evaluate your job readiness score, and get instant, structured critique calibrated against top engineering standards.
        </p>

        {/* CTA Actions */}
        <div className="mt-10 flex flex-col sm:flex-row items-center gap-4 w-full justify-center">
          <Link
            href="/dashboard"
            className="w-full sm:w-auto px-8 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 font-semibold text-white text-base shadow-lg shadow-indigo-500/25 transition-all hover:-translate-y-0.5"
          >
            Launch Candidate Dashboard
          </Link>
          <Link
            href="/login"
            className="w-full sm:w-auto px-8 py-3.5 rounded-xl border border-slate-700 hover:border-slate-600 bg-slate-900/60 hover:bg-slate-800 font-semibold text-slate-200 text-base transition-all"
          >
            Sign In with Supabase
          </Link>
        </div>

        {/* Feature Grid */}
        <div className="mt-20 grid grid-cols-1 md:grid-cols-3 gap-6 w-full text-left">
          <div className="p-6 rounded-2xl border border-slate-800/80 bg-slate-900/40 hover:border-indigo-500/30 transition-all">
            <div className="w-12 h-12 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 font-bold mb-4">
              🎯
            </div>
            <h3 className="text-lg font-semibold text-slate-100">Adaptive Mock Interviews</h3>
            <p className="mt-2 text-sm text-slate-400 leading-relaxed">
              Tailored behavioral and technical challenges dynamically generated for your target role and seniority.
            </p>
          </div>

          <div className="p-6 rounded-2xl border border-slate-800/80 bg-slate-900/40 hover:border-violet-500/30 transition-all">
            <div className="w-12 h-12 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center text-violet-400 font-bold mb-4">
              📊
            </div>
            <h3 className="text-lg font-semibold text-slate-100">Job Readiness Analyzer</h3>
            <p className="mt-2 text-sm text-slate-400 leading-relaxed">
              Deep evaluation of your answers, identifying key technical blindspots, strength metrics, and score breakdowns.
            </p>
          </div>

          <div className="p-6 rounded-2xl border border-slate-800/80 bg-slate-900/40 hover:border-pink-500/30 transition-all">
            <div className="w-12 h-12 rounded-xl bg-pink-500/10 border border-pink-500/20 flex items-center justify-center text-pink-400 font-bold mb-4">
              📄
            </div>
            <h3 className="text-lg font-semibold text-slate-100">Resume & Document Ingestion</h3>
            <p className="mt-2 text-sm text-slate-400 leading-relaxed">
              Upload your CV or job description to generate questions hyper-focused on your specific career trajectory.
            </p>
          </div>
        </div>

        {/* Status Badge */}
        <div className="mt-16 inline-flex items-center gap-2.5 px-4 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-400">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
          <span>FastAPI & Supabase High-Throughput Engine Active</span>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 py-6 text-center text-xs text-slate-600">
        AI Interview Prep Assistant © 2026. Powered by Next.js & FastAPI.
      </footer>
    </div>
  );
}
