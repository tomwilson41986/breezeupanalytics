export default function LoadingSpinner({ message = "Loading data..." }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-4">
      <div className="relative">
        <div className="w-12 h-12 rounded-full border-2 border-slate-700" />
        <div className="absolute inset-0 w-12 h-12 rounded-full border-2 border-transparent border-t-brand-500 animate-spin" />
      </div>
      <p className="text-sm text-slate-400 animate-pulse-brand">{message}</p>
    </div>
  );
}
