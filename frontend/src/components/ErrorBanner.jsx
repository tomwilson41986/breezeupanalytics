export default function ErrorBanner({ message, onRetry }) {
  return (
    <div className="rounded-xl border border-red-100 bg-red-50 p-6 text-center">
      <p className="text-red-600 font-medium mb-2">Failed to load data</p>
      <p className="text-sm text-gray-500 mb-4">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium transition-colors"
        >
          Retry
        </button>
      )}
    </div>
  );
}
