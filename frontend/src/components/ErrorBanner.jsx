export default function ErrorBanner({ message, onRetry }) {
  return (
    <div className="rounded-xl border border-danger-500/30 bg-danger-500/10 p-6 text-center">
      <p className="text-danger-400 font-medium mb-2">Failed to load data</p>
      <p className="text-sm text-slate-400 mb-4">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium transition-colors"
        >
          Retry
        </button>
      )}
    </div>
  );
}
