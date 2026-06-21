"use client";

import { useEffect, useState } from "react";
import {
  useChapters,
  useCharacters,
  useCreateEvent,
  useLore,
  useUpdateEvent,
} from "@/lib/queries";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { useToast } from "@/components/ui/Toast";
import type { Event } from "@/lib/types";

export function EventForm({
  projectId,
  chapterId,
  event,
}: {
  projectId: number;
  chapterId: number;
  event?: Event;
}) {
  const { data: characters = [] } = useCharacters(projectId);
  const { data: lore = [] } = useLore(projectId);
  const { data: chapters = [] } = useChapters(projectId);
  const locations = lore.filter((l) => l.type === "location");
  const create = useCreateEvent();
  const update = useUpdateEvent(event?.id ?? 0, projectId);
  const toast = useToast();

  const isEdit = event !== undefined;

  const [title, setTitle] = useState(event?.title ?? "");
  const [description, setDescription] = useState(event?.description ?? "");
  const [involved, setInvolved] = useState<number[]>(event?.involved_characters ?? []);
  const [locationId, setLocationId] = useState<number | "">(event?.location_id ?? "");
  const [chapterIdState, setChapterIdState] = useState<number>(
    event?.chapter_id ?? chapterId ?? (chapters[0]?.id ?? 0)
  );

  useEffect(() => {
    if (event) {
      setTitle(event.title);
      setDescription(event.description);
      setInvolved(event.involved_characters || []);
      setLocationId(event.location_id ?? "");
      setChapterIdState(event.chapter_id);
    }
  }, [event?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleChar = (id: number) => {
    setInvolved((cur) =>
      cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]
    );
  };

  const handleSave = async () => {
    if (!title.trim()) {
      toast("请填写标题", "error");
      return;
    }
    if (!description.trim()) {
      toast("请填写描述", "error");
      return;
    }
    try {
      if (isEdit) {
        await update.mutateAsync({
          title, description,
          involved_characters: involved,
          location_id: locationId === "" ? null : locationId,
        });
        toast("已保存", "success");
      } else {
        await create.mutateAsync({
          project_id: projectId,
          chapter_id: chapterIdState,
          title, description,
          involved_characters: involved,
          location_id: locationId === "" ? null : locationId,
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
        {isEdit ? `编辑事件：${event?.title}` : "新建事件"}
      </h2>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">章节</label>
        <select
          aria-label="章节"
          value={chapterIdState}
          onChange={(e) => setChapterIdState(Number(e.target.value))}
          disabled={isEdit}
          className="w-full bg-input border border-line rounded p-2 text-text"
        >
          {chapters.map((c) => (
            <option key={c.id} value={c.id}>
              第 {c.order_index} 章 · {c.title || "(无标题)"}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">标题</label>
        <input
          aria-label="标题"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="≤20 字"
          maxLength={50}
          className="w-full bg-input border border-line rounded p-2 text-text"
        />
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">描述</label>
        <textarea
          aria-label="描述"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
          className="w-full bg-input border border-line rounded p-2 text-text"
        />
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">涉及人物</label>
        <div className="flex flex-wrap gap-1">
          {characters.map((c) => (
            <Chip
              key={c.id}
              selected={involved.includes(c.id)}
              onClick={() => toggleChar(c.id)}
            >
              {c.name}
            </Chip>
          ))}
        </div>
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">地点</label>
        <select
          aria-label="地点"
          value={locationId}
          onChange={(e) =>
            setLocationId(e.target.value === "" ? "" : Number(e.target.value))
          }
          className="w-full bg-input border border-line rounded p-2 text-text"
        >
          <option value="">（无）</option>
          {locations.map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
        </select>
      </div>

      <Button
        variant="primary"
        onClick={handleSave}
        disabled={create.isPending || update.isPending}
      >
        {isEdit ? "保存修改" : "新建"}
      </Button>
    </div>
  );
}
