export default function LoadingSpinner({ message = "Loading data..." }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-4">
      <div className="relative">
        <div className="w-10 h-10 rounded-full border-2 border-gray-200" />
        <div className="absolute inset-0 w-10 h-10 rounded-full border-2 border-transparent border-t-brand-600 animate-spin" />
      </div>
      <p className="text-sm text-gray-400 animate-pulse-brand">{message}</p>
    </div>
  );
}
