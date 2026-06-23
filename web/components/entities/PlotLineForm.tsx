"use client";

import { useEffect, useState } from "react";
import {
  useChapters,
  useCreatePlotLine,
  useUpdatePlotLine,
  useProject,
  useGenreTemplates,
} from "@/lib/queries";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import type { PlotLine, PlotLineStatus, PlotLineType } from "@/lib/types";

const TYPES: PlotLineType[] = ["main", "sub"];
const STATUSES: PlotLineStatus[] = ["planned", "active", "resolved", "abandoned"];

const TYPE_LABELS: Record<PlotLineType, string> = { main: "主线", sub: "支线" };
const STATUS_LABELS: Record<PlotLineStatus, string> = {
  planned: "计划中",
  active: "进行中",
  resolved: "已完结",
  abandoned: "已废弃",
};

export function PlotLineForm({
  projectId,
  plotLine,
}: {
  projectId: number;
  plotLine?: PlotLine;
}) {
  const { data: chapters = [] } = useChapters(projectId);
  const { data: project } = useProject(projectId);
  const { data: genreTemplates } = useGenreTemplates();
  const create = useCreatePlotLine();
  const update = useUpdatePlotLine(plotLine?.id ?? 0, projectId);
  const toast = useToast();
  const genreTpl =
    project?.genre && genreTemplates ? genreTemplates[project.genre] ?? null : null;

  const isEdit = plotLine !== undefined;

  const [type, setType] = useState<PlotLineType>(plotLine?.type ?? "sub");
  const [title, setTitle] = useState(plotLine?.title ?? "");
  const [summary, setSummary] = useState(plotLine?.summary ?? "");
  const [description, setDescription] = useState(plotLine?.description ?? "");
  const [statusVal, setStatusVal] = useState<PlotLineStatus>(plotLine?.status ?? "planned");
  const [startCh, setStartCh] = useState<number | "">(plotLine?.start_chapter ?? "");
  const [endCh, setEndCh] = useState<number | "">(plotLine?.end_chapter ?? "");

  useEffect(() => {
    if (plotLine) {
      setType(plotLine.type);
      setTitle(plotLine.title);
      setSummary(plotLine.summary);
      setDescription(plotLine.description);
      setStatusVal(plotLine.status);
      setStartCh(plotLine.start_chapter ?? "");
      setEndCh(plotLine.end_chapter ?? "");
    }
  }, [plotLine?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSave = async () => {
    if (!title.trim()) {
      toast("请填写标题", "error");
      return;
    }
    try {
      if (isEdit) {
        await update.mutateAsync({
          type,
          title,
          summary,
          description,
          status: statusVal,
          start_chapter: startCh === "" ? null : startCh,
          end_chapter: endCh === "" ? null : endCh,
        });
        toast("已保存", "success");
      } else {
        await create.mutateAsync({
          project_id: projectId,
          type,
          title,
          summary,
          description,
          status: statusVal,
          start_chapter: startCh === "" ? null : startCh,
          end_chapter: endCh === "" ? null : endCh,
        });
        toast("已新建", "success");
      }
    } catch (e) {
      toast(`保存失败: ${(e as Error).message}`, "error");
    }
  };

  return (
    <div className="p-4 space-y-3 max-w-2xl">
      <h2 className="text-lg">{isEdit ? `编辑：${plotLine?.title}` : "新建情节线"}</h2>

      <div className="flex gap-2">
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">类型</label>
          <select
            aria-label="类型"
            value={type}
            onChange={(e) => setType(e.target.value as PlotLineType)}
            className="w-full bg-input border border-line rounded p-2 text-text"
          >
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {TYPE_LABELS[t]}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">状态</label>
          <select
            aria-label="状态"
            value={statusVal}
            onChange={(e) => setStatusVal(e.target.value as PlotLineStatus)}
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
        <label className="text-xs text-text-muted-bright block mb-1">标题</label>
        <input
          aria-label="标题"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="w-full bg-input border border-line rounded p-2 text-text"
        />
        {genreTpl && genreTpl.plot_templates.length > 0 && (
          <div className="text-xs text-text-dim mt-1">
            💡 常见流派：
            {genreTpl.plot_templates.map((plt) => (
              <button
                key={plt}
                type="button"
                onClick={() => setTitle(plt)}
                className="inline-block px-2 py-0.5 mr-1 mt-1 rounded bg-input border border-line hover:bg-hover"
              >
                {plt}
              </button>
            ))}
          </div>
        )}
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">概述（当前进展）</label>
        <textarea
          aria-label="概述"
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          rows={2}
          className="w-full bg-input border border-line rounded p-2 text-text"
        />
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">描述（静态）</label>
        <textarea
          aria-label="描述"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          className="w-full bg-input border border-line rounded p-2 text-text"
        />
      </div>

      <div className="flex gap-2">
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">起始章</label>
          <select
            aria-label="起始章"
            value={startCh}
            onChange={(e) => setStartCh(e.target.value === "" ? "" : Number(e.target.value))}
            className="w-full bg-input border border-line rounded p-2 text-text"
          >
            <option value="">（未指定）</option>
            {chapters.map((c) => (
              <option key={c.id} value={c.id}>
                第 {c.order_index} 章 · {c.title}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">结束章</label>
          <select
            aria-label="结束章"
            value={endCh}
            onChange={(e) => setEndCh(e.target.value === "" ? "" : Number(e.target.value))}
            className="w-full bg-input border border-line rounded p-2 text-text"
          >
            <option value="">（未结束）</option>
            {chapters.map((c) => (
              <option key={c.id} value={c.id}>
                第 {c.order_index} 章 · {c.title}
              </option>
            ))}
          </select>
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
