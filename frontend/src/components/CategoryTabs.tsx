import type { Category } from "@/lib/types";

interface Props {
  categories: Category[];
  selected: string | null;
  onSelect: (category: string | null) => void;
}

const CHIP_BASE =
  "rounded-full px-4 py-2 text-[13px] font-bold tracking-[0.3px] transition-colors duration-150 whitespace-nowrap";
const CHIP_ACTIVE = "bg-accent text-white";
const CHIP_INACTIVE = "bg-surface-card text-ink hover:bg-surface-soft";

export default function CategoryTabs({ categories, selected, onSelect }: Props) {
  const totalCount = categories.reduce((sum, c) => sum + c.product_count, 0);

  return (
    <div className="flex flex-wrap gap-2">
      <button onClick={() => onSelect(null)} className={`${CHIP_BASE} ${selected === null ? CHIP_ACTIVE : CHIP_INACTIVE}`}>
        All <span className="font-mono tabular-nums">({totalCount})</span>
      </button>
      {categories.map((c) => (
        <button
          key={c.category}
          onClick={() => onSelect(c.category)}
          className={`${CHIP_BASE} capitalize ${selected === c.category ? CHIP_ACTIVE : CHIP_INACTIVE}`}
        >
          {c.category.replace("_", " ")} <span className="font-mono tabular-nums">({c.product_count})</span>
        </button>
      ))}
    </div>
  );
}
