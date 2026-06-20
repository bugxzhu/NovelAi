"use client";

import { useEffect, useState } from "react";
import {
  useCharacters,
  useCreateRelationship,
  useUpdateRelationship,
} from "@/lib/queries";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import type { Relationship } from "@/lib/types";

export function RelationshipForm({
  projectId,
  relationship,
}: {
  projectId: number;
  relationship?: Relationship;
}) {
  const { data: characters = [] } = useCharacters(projectId);
  const create = useCreateRelationship();
  const update = useUpdateRelationship(relationship?.id ?? 0, projectId);
  const toast = useToast();

  const isEdit = relationship !== undefined;

  const [fromId, setFromId] = useState<number | "">(relationship?.from_char_id ?? "");
  const [toId, setToId] = useState<number | "">(relationship?.to_char_id ?? "");
  const [type, setType] = useState(relationship?.type ?? "");
  const [strength, setStrength] = useState(relationship?.strength ?? 0);
  const [description, setDescription] = useState(relationship?.description ?? "");
  const [validFrom, setValidFrom] = useState(relationship?.valid_from_chapter ?? 0);

  useEffect(() => {
    if (relationship) {
      setFromId(relationship.from_char_id);
      setToId(relationship.to_char_id);
      setType(relationship.type);
      setStrength(relationship.strength);
      setDescription(relationship.description);
      setValidFrom(relationship.valid_from_chapter);
    }
  }, [relationship?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSave = async () => {
    if (fromId === "" || toId === "") {
      toast("请选择 From 和 To 人物", "error");
      return;
    }
    if (fromId === toId) {
      toast("From 和 To 不能是同一人物", "error");
      return;
    }
    if (!type.trim()) {
      toast("请填写关系类型", "error");
      return;
    }

    try {
      if (isEdit) {
        await update.mutateAsync({ type, strength, description });
        toast("已保存", "success");
      } else {
        await create.mutateAsync({
          project_id: projectId,
          from_char_id: fromId as number,
          to_char_id: toId as number,
          type,
          strength,
          description,
          valid_from_chapter: validFrom,
        });
        toast("已新建", "success");
      }
    } catch (e) {
      toast(`保存失败: ${(e as Error).message}`, "error");
    }
  };

  return (
    <div className="p-4 space-y-3 max-w-2xl">
      <h2 className="text-lg">
        {isEdit ? `编辑关系：${relationship?.from_char_name} → ${relationship?.to_char_name}` : "新建关系"}
      </h2>

      <div className="flex gap-2">
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">From</label>
          <select
            aria-label="From"
            value={fromId}
            onChange={(e) => setFromId(Number(e.target.value))}
            disabled={isEdit}
            className="w-full bg-input border border-line rounded p-2 text-text"
          >
            <option value="">选择人物...</option>
            {characters.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">To</label>
          <select
            aria-label="To"
            value={toId}
            onChange={(e) => setToId(Number(e.target.value))}
            disabled={isEdit}
            className="w-full bg-input border border-line rounded p-2 text-text"
          >
            <option value="">选择人物...</option>
            {characters.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">类型</label>
        <input
          value={type}
          onChange={(e) => setType(e.target.value)}
          placeholder="仇人 / 旧友 / 师徒 / ..."
          className="w-full bg-input border border-line rounded p-2 text-text"
        />
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">
          强度（{strength.toFixed(2)}）
        </label>
        <input
          type="range"
          min={-1}
          max={1}
          step={0.1}
          value={strength}
          onChange={(e) => setStrength(Number(e.target.value))}
          className="w-full"
        />
        <div className="flex justify-between text-[10px] text-text-dim">
          <span>-1.0 敌对</span>
          <span>0.0 中立</span>
          <span>+1.0 亲密</span>
        </div>
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">描述</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          className="w-full bg-input border border-line rounded p-2 text-text"
        />
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">生效章</label>
        <input
          aria-label="生效章"
          type="number"
          min={0}
          value={validFrom}
          onChange={(e) => setValidFrom(Number(e.target.value))}
          disabled={isEdit}
          className="w-24 bg-input border border-line rounded p-2 text-text"
        />
        <span className="text-xs text-text-dim ml-2">0 = 开章前</span>
      </div>

      <Button variant="primary" onClick={handleSave} disabled={create.isPending || update.isPending}>
        {isEdit ? "保存修改" : "新建"}
      </Button>
    </div>
  );
}
