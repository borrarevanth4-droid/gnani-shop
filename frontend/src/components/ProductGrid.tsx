"use client";

import { PackageSearch } from "lucide-react";
import type { Product } from "@/lib/types";
import Button from "@/components/ui/Button";
import EmptyState from "@/components/ui/EmptyState";
import { SkeletonCards } from "@/components/ui/Skeleton";
import { useI18n } from "@/lib/i18n";

interface Props {
  products: Product[];
  onAdd: (sku: string) => void;
  onView: (product: Product) => void;
  addingSku: string | null;
  loading?: boolean;
}

export default function ProductGrid({ products, onAdd, onView, addingSku, loading = false }: Props) {
  const { t, lang } = useI18n();
  if (loading) return <SkeletonCards count={8} className="sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" />;

  if (products.length === 0) {
    return (
      <EmptyState
        icon={PackageSearch}
        title="No products match your filters"
        description="Try a different search term, or clear the category filter."
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-3">
      {products.map((p) => (
        <div key={p.sku} className="flex flex-col justify-between rounded-md bg-surface-card p-6">
          <button onClick={() => onView(p)} className="text-left">
            <p className="text-[12px] font-medium uppercase tracking-[0.6px] text-ink-faint">{p.brand}</p>
            <h3 className="display mt-1 text-[20px] leading-snug text-ink hover:text-accent">{p.name}</h3>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="text-[13px] text-ink-soft">{p.unit}</span>
              {lang !== "en-IN" && p.aliases?.[lang] && (
                <span className="rounded-full bg-accent px-2.5 py-0.5 text-[12px] font-medium text-white">{p.aliases[lang]}</span>
              )}
            </div>
            {p.discount_pct ? (
              <p className="mt-4 flex items-baseline gap-2">
                <span className="font-mono text-sm tabular-nums text-ink-faint line-through">{p.price_display}</span>
                <span className="text-[24px] font-semibold tabular-nums text-commerce">{p.effective_price_display}</span>
                <span className="text-xs font-bold text-commerce">-{p.discount_pct}%</span>
              </p>
            ) : (
              <p className="mt-4 text-[24px] font-semibold tabular-nums text-ink">{p.price_display}</p>
            )}
            <p className="mt-0.5 text-[13px] text-ink-faint">{p.stock > 0 ? `${t("inStock")} · ${p.stock}` : t("outOfStock")}</p>
          </button>
          <Button variant="commerce" onClick={() => onAdd(p.sku)} disabled={p.stock === 0 || addingSku === p.sku} className="mt-5 w-full">
            {addingSku === p.sku ? "…" : t("add")}
          </Button>
        </div>
      ))}
    </div>
  );
}
