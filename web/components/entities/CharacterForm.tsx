"use client";

import { useEffect, useState } from "react";
import { useUpdateCharacter, useDeleteCharacter, useLore } from "@/lib/queries";
import { debounce } from "@/lib/debounce";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { useToast } from "@/components/ui/Toast";
import type { Character, CharacterUpdate } from "@/lib/types";

const TEXT_FIELDS: Array<{ key: keyof CharacterUpdate; label: string }> = [
  { key: "name", label: "姓名" },
  { key: "role", label: "角色" },
  { key: "speech_style", label: "说话风格" },
  { key: "background", label: "背景" },
  { key: "motivation", label: "动机" },
  { key: "appearance", label: "外貌" },
  { key: "current_state", label: "当前状态" },
];

export function CharacterForm({
  projectId,
  character,
  onDeleted,
}: {
  projectId: number;
  character?: Character;
  onDeleted?: () => void;
}) {
  const update = useUpdateCharacter(character?.id ?? 0, projectId);
  const del = useDeleteCharacter(projectId);
  const toast = useToast();
  const { data: lore } = useLore(projectId);
  const factions = (lore ?? []).filter((l) => l.type === "faction");
  const locations = (lore ?? []).filter((l) => l.type === "location");

  const [form, setForm] = useState<CharacterUpdate>({});

  useEffect(() => {
    if (character) {
      setForm({
        name: character.name,
        role: character.role,
        speech_style: character.speech_style,
        background: character.background,
        motivation: character.motivation,
        appearance: character.appearance,
        current_state: character.current_state,
        affiliations: character.affiliations,
        known_locations: character.known_locations,
      });
    }
  }, [character?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = debounce((value: CharacterUpdate) => {
    if (!character) return;
    update.mutate(value, {
      onError: (e) => toast(`保存失败: ${(e as Error).message}`, "error"),
    });
  }, 500);

  const setText = (key: keyof CharacterUpdate, v: string) => {
    const next = { ...form, [key]: v };
    setForm(next);
    save(next);
  };

  const toggleAff = (id: number) => {
    if (!character) return;
    const current = form.affiliations ?? character.affiliations ?? [];
    const next = current.includes(id)
      ? current.filter((x) => x !== id)
      : [...current, id];
    setForm({ ...form, affiliations: next });
    save({ ...form, affiliations: next });
  };

  const toggleLoc = (id: number) => {
    if (!character) return;
    const current = form.known_locations ?? character.known_locations ?? [];
    const next = current.includes(id)
      ? current.filter((x) => x !== id)
      : [...current, id];
    setForm({ ...form, known_locations: next });
    save({ ...form, known_locations: next });
  };

  if (!character) {
    return <div className="p-4 text-[#888]">请从左侧选择或新建人物</div>;
  }

  return (
    <div className="p-4 space-y-4 max-w-2xl">
      <div className="flex items-center justify-between">
        <h2 className="text-lg">{form.name || character.name || "未命名"}</h2>
        <Button
          variant="danger"
          onClick={() => {
            if (!confirm(`删除人物 "${character.name}"？此操作不可撤销。`)) return;
            del.mutate(character.id, {
              onSuccess: () => onDeleted?.(),
              onError: (e) => toast(`删除失败: ${(e as Error).message}`, "error"),
            });
          }}
        >
          删除
        </Button>
      </div>

      {TEXT_FIELDS.map((f) => (
        <div key={f.key}>
          <label className="text-xs text-[#aaa] block mb-1">{f.label}</label>
          <input
            value={(form[f.key] as string) ?? ""}
            onChange={(e) => setText(f.key, e.target.value)}
            className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
          />
        </div>
      ))}

      <div>
        <label className="text-xs text-[#aaa] block mb-1">所属势力</label>
        <div className="flex flex-wrap gap-1">
          {factions.map((f) => (
            <Chip
              key={f.id}
              selected={(form.affiliations ?? character.affiliations ?? []).includes(f.id)}
              onClick={() => toggleAff(f.id)}
            >
              {f.name}
            </Chip>
          ))}
        </div>
      </div>

      <div>
        <label className="text-xs text-[#aaa] block mb-1">活动地点</label>
        <div className="flex flex-wrap gap-1">
          {locations.map((l) => (
            <Chip
              key={l.id}
              selected={(form.known_locations ?? character.known_locations ?? []).includes(l.id)}
              onClick={() => toggleLoc(l.id)}
            >
              {l.name}
            </Chip>
          ))}
        </div>
      </div>
    </div>
  );
}
