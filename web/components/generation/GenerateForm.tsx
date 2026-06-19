"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useCharacters, useLore } from "@/lib/queries";
import { useGenerateParams } from "@/lib/store";
import { useGenerate } from "./useGenerate";
import { Chip } from "@/components/ui/Chip";
import { Button } from "@/components/ui/Button";
import type { ModelTask } from "@/lib/types";

export function GenerateForm({ chapterId }: { chapterId: number }) {
  const params = useParams<{ projectId: string }>();
  const pid = Number(params.projectId);
  const { data: characters } = useCharacters(pid);
  const { data: lore } = useLore(pid);
  const locations = (lore ?? []).filter((l) => l.type === "location");

  const { involvedCharacterIds, locationId, setParams } = useGenerateParams();
  const [beatText, setBeatText] = useState("");
  const [instruction, setInstruction] = useState("");
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
        <label className="text-xs text-[#aaa] block mb-1">Beat 文本 *</label>
        <textarea
          value={beatText}
          onChange={(e) => setBeatText(e.target.value)}
          placeholder="例：李雷推开残月酒馆的门，看见多年未见的韩梅在角落等候"
          rows={3}
          maxLength={2000}
          className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
        />
        <div className="text-xs text-[#666] mt-1">{beatText.length}/2000</div>
      </div>

      <div>
        <label className="text-xs text-[#aaa] block mb-1">涉及人物 *（1-20）</label>
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
        <label className="text-xs text-[#aaa] block mb-1">地点</label>
        <select
          value={locationId ?? ""}
          onChange={(e) =>
            setParams({ locationId: e.target.value ? Number(e.target.value) : null })
          }
          className="bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 w-full text-[#cccccc]"
        >
          <option value="">（无）</option>
          {locations.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="text-xs text-[#aaa] block mb-1">附加指令</label>
        <textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="例：氛围压抑，对话简短"
          rows={2}
          maxLength={500}
          className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
        />
      </div>

      <div>
        <label className="text-xs text-[#aaa] block mb-1">模型任务</label>
        <select
          value={modelTask}
          onChange={(e) => setModelTask(e.target.value as ModelTask)}
          className="bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 w-48 text-[#cccccc]"
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
