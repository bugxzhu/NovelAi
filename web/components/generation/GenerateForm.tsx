"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useCharacters, useLore, useCreateLore } from "@/lib/queries";
import { useGenerateParams, useBeatDraftStore } from "@/lib/store";
import { useGenerate } from "./useGenerate";
import { Chip } from "@/components/ui/Chip";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import type { ModelTask } from "@/lib/types";

export function GenerateForm({ chapterId }: { chapterId: number }) {
  const params = useParams<{ projectId: string }>();
  const pid = Number(params.projectId);
  const { data: characters } = useCharacters(pid);
  const { data: lore } = useLore(pid);
  const locations = (lore ?? []).filter((l) => l.type === "location");
  const createLore = useCreateLore();
  const toast = useToast();
  const [showNewLocation, setShowNewLocation] = useState(false);
  const [newLocName, setNewLocName] = useState("");
  const [newLocDesc, setNewLocDesc] = useState("");

  const handleCreateLocation = async () => {
    if (!newLocName.trim()) return;
    try {
      const loc = await createLore.mutateAsync({
        project_id: pid,
        type: "location",
        name: newLocName.trim(),
        description: newLocDesc.trim(),
      });
      setParams({ locationId: loc.id });
      setNewLocName("");
      setNewLocDesc("");
      setShowNewLocation(false);
      toast(`已创建地点：${loc.name}`, "success");
    } catch (e) {
      toast(`创建失败: ${(e as Error).message}`, "error");
    }
  };

  const { involvedCharacterIds, locationId, setParams } = useGenerateParams();
  // Beat + instruction drafts persist across tab switches via the per-chapter store;
  // cleared on Accept (see StreamView.handleAccept).
  const beatText = useBeatDraftStore((s) => s.chapters[chapterId]?.beatText ?? "");
  const instruction = useBeatDraftStore((s) => s.chapters[chapterId]?.instruction ?? "");
  const setBeatText = useBeatDraftStore((s) => s.setBeatText);
  const setInstruction = useBeatDraftStore((s) => s.setInstruction);
  const [modelTask, setModelTask] = useState<ModelTask>("writer_long");

  const { start, cancel, status } = useGenerate(chapterId);

  const toggleChar = (id: number) => {
    const next = involvedCharacterIds.includes(id)
      ? involvedCharacterIds.filter((x) => x !== id)
      : [...involvedCharacterIds, id].slice(0, 20);
    setParams({ involvedCharacterIds: next });
  };

  const handleSubmit = async () => {
    try {
      await start({
        beat_text: beatText,
        instruction,
        involved_character_ids: involvedCharacterIds,
        location_id: locationId,
        model_task: modelTask,
        max_tokens: 4096,
      });
    } catch {
      // Error already captured in shared generation state; StreamView displays it
    }
  };

  const isStreaming = status === "preparing" || status === "streaming";

  return (
    <div className="space-y-3 text-sm">
      <div>
        <label className="text-xs text-text-muted-bright block mb-1">Beat 文本 *</label>
        <textarea
          value={beatText}
          onChange={(e) => setBeatText(chapterId, e.target.value)}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
              e.preventDefault();
              if (!isStreaming && beatText.trim() && involvedCharacterIds.length > 0) {
                handleSubmit();
              }
            }
          }}
          placeholder="例：李雷推开残月酒馆的门，看见多年未见的韩梅在角落等候"
          rows={3}
          maxLength={2000}
          className="w-full bg-input border border-line rounded p-2 text-text"
        />
        <div className="text-xs text-text-dim mt-1 flex justify-between">
          <span>{beatText.length}/2000</span>
          <span>Ctrl+Enter 快速生成</span>
        </div>
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">涉及人物 *（1-20）</label>
        <div className="flex flex-wrap gap-1">
          {(characters ?? []).map((c) => (
            <Chip
              key={c.id}
              selected={involvedCharacterIds.includes(c.id)}
              onClick={() => toggleChar(c.id)}
            >
              {c.name}（{c.role}）
            </Chip>
          ))}
        </div>
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">地点（可选）</label>
        <div className="flex gap-1">
          <select
            value={locationId ?? ""}
            onChange={(e) =>
              setParams({ locationId: e.target.value ? Number(e.target.value) : null })
            }
            className="bg-input border border-line rounded p-2 w-full text-text"
          >
            <option value="">（无，直接生成）</option>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
          {!showNewLocation && (
            <button
              type="button"
              onClick={() => setShowNewLocation(true)}
              title="新建地点"
              className="px-2 py-1 rounded text-sm bg-button hover:bg-button-hover text-text shrink-0"
            >
              +
            </button>
          )}
        </div>
        {showNewLocation && (
          <div className="mt-1 p-2 border border-line rounded bg-input/30 space-y-2">
            <input
              value={newLocName}
              onChange={(e) => setNewLocName(e.target.value)}
              placeholder="地点名称（如：残月酒馆）"
              className="w-full bg-input border border-line rounded px-2 py-1 text-sm text-text"
            />
            <input
              value={newLocDesc}
              onChange={(e) => setNewLocDesc(e.target.value)}
              placeholder="简短描述（可选）"
              className="w-full bg-input border border-line rounded px-2 py-1 text-sm text-text"
            />
            <div className="flex gap-2">
              <Button
                variant="primary"
                onClick={handleCreateLocation}
                disabled={createLore.isPending || !newLocName.trim()}
              >
                创建
              </Button>
              <Button variant="ghost" onClick={() => setShowNewLocation(false)}>
                取消
              </Button>
            </div>
          </div>
        )}
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">附加指令</label>
        <textarea
          value={instruction}
          onChange={(e) => setInstruction(chapterId, e.target.value)}
          placeholder="例：氛围压抑，对话简短"
          rows={2}
          maxLength={500}
          className="w-full bg-input border border-line rounded p-2 text-text"
        />
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">模型任务</label>
        <select
          value={modelTask}
          onChange={(e) => setModelTask(e.target.value as ModelTask)}
          className="bg-input border border-line rounded p-2 w-48 text-text"
        >
          <option value="writer_long">writer_long（高质量）</option>
          <option value="writer_short">writer_short（快速）</option>
        </select>
      </div>

      <div className="flex gap-2 pt-2">
        {isStreaming ? (
          <Button variant="danger" onClick={cancel}>
            ✕ 取消
          </Button>
        ) : (
          <Button
            variant="primary"
            onClick={handleSubmit}
            disabled={!beatText.trim() || involvedCharacterIds.length === 0}
          >
            ✨ 生成
          </Button>
        )}
      </div>
    </div>
  );
}
