"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useLore, useUpdateLore, useDeleteLore } from "@/lib/queries";
import { debounce } from "@/lib/debounce";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import type { LoreEntry, LoreUpdate, LoreType } from "@/lib/types";

const TEXT_FIELDS: Array<{ key: keyof LoreUpdate; label: string; rows?: number }> = [
  { key: "name", label: "名称" },
  { key: "title", label: "别名" },
  { key: "description", label: "描述", rows: 4 },
];

export function LoreForm({
  projectId,
  lore,
  onDeleted,
}: {
  projectId: number;
  lore?: LoreEntry;
  onDeleted?: () => void;
}) {
  const update = useUpdateLore(lore?.id ?? 0, projectId);
  const del = useDeleteLore(projectId);
  const { data: allLore } = useLore(projectId);
  const toast = useToast();

  const [form, setForm] = useState<LoreUpdate>({});

  useEffect(() => {
    if (lore) {
      setForm({
        type: lore.type,
        name: lore.name,
        title: lore.title,
        description: lore.description,
        parent_id: lore.parent_id,
      });
    }
  }, [lore?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Capture the latest mutation/toast/lore in refs so the stable debounced fn
  // (created once via useMemo) always calls into the current closure rather than a
  // stale one. Without this, recreating debounce() per render strands pending
  // timers from prior renders and can fire stale trailing saves.
  const updateRef = useRef(update);
  updateRef.current = update;
  const toastRef = useRef(toast);
  toastRef.current = toast;
  const loreRef = useRef(lore);
  loreRef.current = lore;

  const save = useMemo(
    () =>
      debounce((value: LoreUpdate) => {
        if (!loreRef.current) return;
        updateRef.current.mutate(value, {
          onError: (e) => toastRef.current(`保存失败: ${(e as Error).message}`, "error"),
        });
      }, 500),
    []
  );

  const setText = (key: keyof LoreUpdate, v: string) => {
    const next = { ...form, [key]: v };
    setForm(next);
    save(next);
  };

  if (!lore) {
    return <div className="p-4 text-text-muted">请从左侧选择或新建条目</div>;
  }

  // For locations, parent candidates are other locations of same project (excluding self + descendants)
  const sameTypeLocations = (allLore ?? []).filter(
    (l) => l.type === "location" && l.id !== lore.id
  );

  return (
    <div className="p-4 space-y-4 max-w-2xl">
      <div className="flex items-center justify-between">
        <h2 className="text-lg">{form.name || lore.name || "未命名"}</h2>
        <Button
          variant="danger"
          onClick={() => {
            if (!confirm(`删除 "${lore.name}"？`)) return;
            del.mutate(lore.id, {
              onSuccess: () => onDeleted?.(),
              onError: (e) => toast(`删除失败: ${(e as Error).message}`, "error"),
            });
          }}
        >
          删除
        </Button>
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">类型</label>
        <select
          value={(form.type as LoreType) ?? lore.type}
          onChange={(e) => {
            const v = e.target.value as LoreType;
            setForm({ ...form, type: v });
            save({ ...form, type: v });
          }}
          className="bg-input border border-line rounded p-2 text-text"
        >
          <option value="location">地点</option>
          <option value="faction">势力</option>
          <option value="item">物品</option>
          <option value="organization">组织</option>
          <option value="concept">概念</option>
          <option value="custom">自定义</option>
        </select>
      </div>

      {TEXT_FIELDS.map((f) => (
        <div key={f.key}>
          <label className="text-xs text-text-muted-bright block mb-1">{f.label}</label>
          {f.rows ? (
            <textarea
              value={(form[f.key] as string) ?? ""}
              onChange={(e) => setText(f.key, e.target.value)}
              rows={f.rows}
              className="w-full bg-input border border-line rounded p-2 text-text"
            />
          ) : (
            <input
              value={(form[f.key] as string) ?? ""}
              onChange={(e) => setText(f.key, e.target.value)}
              className="w-full bg-input border border-line rounded p-2 text-text"
            />
          )}
        </div>
      ))}

      {lore.type === "location" && (
        <div>
          <label className="text-xs text-text-muted-bright block mb-1">上级地点</label>
          <select
            value={form.parent_id ?? lore.parent_id ?? ""}
            onChange={(e) => {
              const v = e.target.value ? Number(e.target.value) : null;
              setForm({ ...form, parent_id: v });
              save({ ...form, parent_id: v });
            }}
            className="bg-input border border-line rounded p-2 text-text"
          >
            <option value="">（顶级）</option>
            {sameTypeLocations.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
