"use client";

import { useEffect, useState } from "react";
import { useWorldOverview, useUpdateWorldOverview } from "@/lib/queries";
import { debounce } from "@/lib/debounce";
import { useToast } from "@/components/ui/Toast";
import type { WorldOverviewUpdate } from "@/lib/types";

const FIELDS: Array<{ key: keyof WorldOverviewUpdate; label: string; rows?: number }> = [
  { key: "setting_era", label: "时代/纪元" },
  { key: "power_system", label: "力量体系" },
  { key: "rules_and_taboos", label: "规则与禁忌", rows: 3 },
  { key: "geography_summary", label: "地理概述", rows: 3 },
  { key: "history_summary", label: "历史概述", rows: 3 },
  { key: "culture_summary", label: "文化概述", rows: 3 },
];

export function WorldOverviewForm({ projectId }: { projectId: number }) {
  const { data, isLoading } = useWorldOverview(projectId);
  const update = useUpdateWorldOverview(projectId);
  const toast = useToast();
  const [form, setForm] = useState<WorldOverviewUpdate>({});

  useEffect(() => {
    if (data) {
      setForm({
        setting_era: data.setting_era,
        power_system: data.power_system,
        rules_and_taboos: data.rules_and_taboos,
        geography_summary: data.geography_summary,
        history_summary: data.history_summary,
        culture_summary: data.culture_summary,
      });
    }
  }, [data]);

  const save = debounce((value: WorldOverviewUpdate) => {
    update.mutate(value, {
      onError: (e) => toast(`保存失败: ${(e as Error).message}`, "error"),
    });
  }, 500);

  const handleChange = (key: keyof WorldOverviewUpdate, v: string) => {
    const next = { ...form, [key]: v };
    setForm(next);
    save(next);
  };

  if (isLoading) return <div className="p-4 text-[#888]">加载中...</div>;

  return (
    <div className="p-4 space-y-4 max-w-2xl">
      <h2 className="text-lg">世界观</h2>
      {FIELDS.map((f) => (
        <div key={f.key}>
          <label className="text-xs text-[#aaa] block mb-1">{f.label}</label>
          <textarea
            value={(form[f.key] as string) ?? ""}
            onChange={(e) => handleChange(f.key, e.target.value)}
            rows={f.rows ?? 1}
            className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
          />
        </div>
      ))}
    </div>
  );
}
