"use client";

import { useEffect, useState } from "react";
import {
  useCreateStoryMilestone,
  useUpdateStoryMilestone,
} from "@/lib/queries";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import type { StoryMilestone } from "@/lib/types";

const STATUSES = ["planned", "written", "needs_revision"] as const;
type MilestoneStatus = (typeof STATUSES)[number];

const STATUS_LABELS: Record<MilestoneStatus, string> = {
  planned: "计划中",
  written: "已写",
  needs_revision: "需修改",
};

export function MilestoneForm({
  projectId,
  milestone,
}: {
  projectId: number;
  milestone?: StoryMilestone;
}) {
  const create = useCreateStoryMilestone();
  const update = useUpdateStoryMilestone(milestone?.id ?? 0, projectId);
  const toast = useToast();

  const isEdit = milestone !== undefined;

  const [orderIndex, setOrderIndex] = useState<number>(milestone?.order_index ?? 0);
  const [type, setType] = useState<string>(milestone?.type ?? "里程碑");
  const [title, setTitle] = useState(milestone?.title ?? "");
  const [description, setDescription] = useState(milestone?.description ?? "");
  const [chapterStart, setChapterStart] = useState<number | "">(milestone?.chapter_start ?? "");
  const [chapterEnd, setChapterEnd] = useState<number | "">(milestone?.chapter_end ?? "");
  const [statusVal, setStatusVal] = useState<MilestoneStatus>(
    (milestone?.status as MilestoneStatus) ?? "planned",
  );

  useEffect(() => {
    if (milestone) {
      setOrderIndex(milestone.order_index);
      setType(milestone.type);
      setTitle(milestone.title);
      setDescription(milestone.description);
      setChapterStart(milestone.chapter_start ?? "");
      setChapterEnd(milestone.chapter_end ?? "");
      setStatusVal(milestone.status as MilestoneStatus);
    }
  }, [milestone?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSave = async () => {
    if (!title.trim()) {
      toast("请填写标题", "error");
      return;
    }
    try {
      if (isEdit) {
        await update.mutateAsync({
          order_index: orderIndex,
          type,
          title,
          description,
          chapter_start: chapterStart === "" ? null : chapterStart,
          chapter_end: chapterEnd === "" ? null : chapterEnd,
          status: statusVal,
        });
        toast("已保存", "success");
      } else {
        await create.mutateAsync({
          project_id: projectId,
          order_index: orderIndex,
          type,
          title,
          description,
          chapter_start: chapterStart === "" ? null : chapterStart,
          chapter_end: chapterEnd === "" ? null : chapterEnd,
          status: statusVal,
        });
        toast("已新建", "success");
      }
    } catch (e) {
      toast(`保存失败: ${(e as Error).message}`, "error");
    }
  };

  return (
    <div className="p-4 space-y-3 max-w-2xl">
      <h2 className="text-lg">{isEdit ? `编辑：${milestone?.title}` : "新建里程碑"}</h2>

      <div className="flex gap-2">
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">顺序</label>
          <input
            type="number"
            aria-label="顺序"
            value={orderIndex}
            onChange={(e) => setOrderIndex(Number(e.target.value))}
            className="w-full bg-input border border-line rounded p-2 text-text"
          />
        </div>
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">状态</label>
          <select
            aria-label="状态"
            value={statusVal}
            onChange={(e) => setStatusVal(e.target.value as MilestoneStatus)}
            className="w-full bg-input border border-line rounded p-2 text-text"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">类型</label>
        <input
          aria-label="类型"
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="w-full bg-input border border-line rounded p-2 text-text"
        />
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">标题</label>
        <input
          aria-label="标题"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="w-full bg-input border border-line rounded p-2 text-text"
        />
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">描述</label>
        <textarea
          aria-label="描述"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={4}
          className="w-full bg-input border border-line rounded p-2 text-text"
        />
      </div>

      <div className="flex gap-2">
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">起始章</label>
          <input
            type="number"
            aria-label="起始章"
            value={chapterStart}
            onChange={(e) => setChapterStart(e.target.value === "" ? "" : Number(e.target.value))}
            className="w-full bg-input border border-line rounded p-2 text-text"
          />
        </div>
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">结束章</label>
          <input
            type="number"
            aria-label="结束章"
            value={chapterEnd}
            onChange={(e) => setChapterEnd(e.target.value === "" ? "" : Number(e.target.value))}
            className="w-full bg-input border border-line rounded p-2 text-text"
          />
        </div>
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
