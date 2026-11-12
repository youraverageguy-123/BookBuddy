/** Placeholder shapes shown while a view loads, so the layout does not jump when content arrives. */
export function PageSkeleton({ label = "Loading view" }: { label?: string }) {
  return <main className="page-frame page-skeleton" role="status" aria-label={label}>
    <span className="skeleton-block skeleton-eyebrow"/>
    <span className="skeleton-block skeleton-title"/>
    <span className="skeleton-block skeleton-line"/>
    <CardGridSkeleton/>
  </main>;
}

export function CardGridSkeleton({ count = 6, label }: { count?: number; label?: string }) {
  return <div className="skeleton-grid" role={label ? "status" : undefined} aria-label={label}>
    {Array.from({ length: count }, (_, index) => <span key={index} className="skeleton-block skeleton-card"/>)}
  </div>;
}
