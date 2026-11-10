"use client";

import { Search } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Input } from "@/components/ui/Input";

interface Props {
  value: string;
  onChange: (value: string) => void;
}

export default function SearchBox({ value, onChange }: Props) {
  const { t } = useI18n();
  return (
    <div className="relative">
      <Search size={18} className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-ink-faint" />
      <Input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={`${t("search")} — atta, दूध, పాలు, நெய்…`}
        className="h-14 rounded-full pl-12 text-base"
      />
    </div>
  );
}
