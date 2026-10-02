export function LoadingRows({ rows = 5 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading" className="skeletons">
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton" />)}
    </div>
  );
}
