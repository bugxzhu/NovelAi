"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  useWorldOverview,
  useUpdateWorldOverview,
  useProject,
  useUpdateProject,
  useGenreTemplates,
} from "@/lib/queries";
import { debounce } from "@/lib/debounce";
import { useToast } from "@/components/ui/Toast";
import type { ProjectUpdate, WorldOverviewUpdate } from "@/lib/types";

const WORLD_FIELDS: Array<{ key: keyof WorldOverviewUpdate; label: string; rows?: number }> = [
  { key: "setting_era", label: "时代/纪元" },
  { key: "power_system", label: "力量体系" },
  { key: "rules_and_taboos", label: "规则与禁忌", rows: 3 },
  { key: "geography_summary", label: "地理概述", rows: 3 },
  { key: "history_summary", label: "历史概述", rows: 3 },
  { key: "culture_summary", label: "文化概述", rows: 3 },
];

interface ProjectFormState {
  title: string;
  genre: string;
  premise: string;
  main_theme: string;
  tone: string;
}

export function WorldOverviewForm({ projectId }: { projectId: number }) {
  const { data, isLoading } = useWorldOverview(projectId);
  const { data: project } = useProject(projectId);
  const { data: genreTemplates } = useGenreTemplates();
  const updateWorld = useUpdateWorldOverview(projectId);
  const updateProject = useUpdateProject(projectId);
  const toast = useToast();
  const [worldForm, setWorldForm] = useState<WorldOverviewUpdate>({});
  const [projectForm, setProjectForm] = useState<ProjectFormState>({
    title: "",
    genre: "",
    premise: "",
    main_theme: "",
    tone: "",
  });

  const genreTpl =
    project?.genre && genreTemplates ? genreTemplates[project.genre] ?? null : null;
  const isPresetGenre = !!(
    genreTemplates &&
    projectForm.genre &&
    projectForm.genre in genreTemplates
  );
  const [genreMode, setGenreMode] = useState<"preset" | "custom">(
    isPresetGenre ? "preset" : "custom"
  );

  useEffect(() => {
    if (data) {
      setWorldForm({
        setting_era: data.setting_era,
        power_system: data.power_system,
        rules_and_taboos: data.rules_and_taboos,
        geography_summary: data.geography_summary,
        history_summary: data.history_summary,
        culture_summary: data.culture_summary,
      });
    }
  }, [data]);

  useEffect(() => {
    if (project) {
      setProjectForm({
        title: project.title,
        genre: project.genre,
        premise: project.premise,
        main_theme: project.main_theme,
        tone: project.tone,
      });
      setGenreMode(
        genreTemplates && project.genre && project.genre in genreTemplates
          ? "preset"
          : "custom"
      );
    }
  }, [project, genreTemplates]);

  // Capture the latest mutations/toast in refs so the stable debounced fns
  // (created once via useMemo) always call into the current closure rather
  // than a stale one. Without this, recreating debounce() per render strands
  // pending timers from prior renders and can fire stale trailing saves.
  const updateWorldRef = useRef(updateWorld);
  updateWorldRef.current = updateWorld;
  const updateProjectRef = useRef(updateProject);
  updateProjectRef.current = updateProject;
  const toastRef = useRef(toast);
  toastRef.current = toast;

  const saveWorld = useMemo(
    () =>
      debounce((value: WorldOverviewUpdate) => {
        updateWorldRef.current.mutate(value, {
          onError: (e) => toastRef.current(`保存失败: ${(e as Error).message}`, "error"),
        });
      }, 500),
    []
  );

  const saveProject = useMemo(
    () =>
      debounce((value: ProjectUpdate) => {
        updateProjectRef.current.mutate(value, {
          onError: (e) => toastRef.current(`保存失败: ${(e as Error).message}`, "error"),
        });
      }, 500),
    []
  );

  const handleWorldChange = (key: keyof WorldOverviewUpdate, v: string) => {
    const next = { ...worldForm, [key]: v };
    setWorldForm(next);
    saveWorld(next);
  };

  const handleProjectChange = (key: keyof ProjectFormState, v: string) => {
    const next = { ...projectForm, [key]: v };
    setProjectForm(next);
    // Only patch changed keys; empty strings are valid as clears
    saveProject({ [key]: v } as ProjectUpdate);
  };

  const applyTemplateDefaults = () => {
    if (!genreTpl) return;
    const next: WorldOverviewUpdate = {
      ...worldForm,
      power_system: genreTpl.world_defaults.power_system,
      rules_and_taboos: genreTpl.world_defaults.rules_and_taboos,
    };
    setWorldForm(next);
    saveWorld(next);
    toast(`已填入「${genreTpl.label}」默认设定`, "success");
  };

  if (isLoading) return <div className="p-4 text-text-muted">加载中...</div>;

  return (
    <div className="p-4 space-y-6 max-w-2xl">
      {/* Project settings section */}
      <div className="space-y-4">
        <h2 className="text-lg">项目设定</h2>

        <div>
          <label className="text-xs text-text-muted-bright block mb-1">标题</label>
          <input
            value={projectForm.title}
            onChange={(e) => handleProjectChange("title", e.target.value)}
            className="w-full bg-input border border-line rounded p-2 text-text"
          />
        </div>

        <div>
          <label className="text-xs text-text-muted-bright block mb-1">类型</label>
          {genreMode === "preset" ? (
            <select
              value={
                projectForm.genre && genreTemplates && projectForm.genre in genreTemplates
                  ? projectForm.genre
                  : "__custom__"
              }
              onChange={(e) => {
                if (e.target.value === "__custom__") {
                  setGenreMode("custom");
                  handleProjectChange("genre", "");
                } else {
                  handleProjectChange("genre", e.target.value);
                }
              }}
              className="w-full bg-input border border-line rounded px-2 py-2 text-sm text-text"
            >
              {!projectForm.genre ||
              !genreTemplates ||
              !(projectForm.genre in genreTemplates) ? null : (
                <option value={projectForm.genre}>
                  {genreTemplates[projectForm.genre]?.label ?? projectForm.genre}
                </option>
              )}
              {genreTemplates &&
                Object.entries(genreTemplates)
                  .filter(([key]) => key !== projectForm.genre)
                  .map(([key, tpl]) => (
                    <option key={key} value={key}>
                      {tpl.label}
                    </option>
                  ))}
              <option value="__custom__">自定义...</option>
            </select>
          ) : (
            <div className="flex gap-1">
              <input
                value={projectForm.genre}
                onChange={(e) => handleProjectChange("genre", e.target.value)}
                placeholder="输入类型"
                className="flex-1 bg-input border border-line rounded px-2 py-2 text-sm text-text"
              />
              <button
                type="button"
                onClick={() => setGenreMode("preset")}
                title="返回预设列表"
                className="px-2 py-2 rounded text-sm bg-button hover:bg-button-hover text-text"
              >
                ▾
              </button>
            </div>
          )}
        </div>

        <div>
          <label className="text-xs text-text-muted-bright block mb-1">
            前提 <span className="text-text-muted">(一句话概括你的故事)</span>
          </label>
          <textarea
            value={projectForm.premise}
            onChange={(e) => handleProjectChange("premise", e.target.value)}
            rows={2}
            className="w-full bg-input border border-line rounded p-2 text-text"
          />
        </div>

        <div>
          <label className="text-xs text-text-muted-bright block mb-1">
            主题 <span className="text-text-muted">(故事的核心主题)</span>
          </label>
          <input
            value={projectForm.main_theme}
            onChange={(e) => handleProjectChange("main_theme", e.target.value)}
            className="w-full bg-input border border-line rounded p-2 text-text"
          />
        </div>

        <div>
          <label className="text-xs text-text-muted-bright block mb-1">
            基调 <span className="text-text-muted">(整体基调)</span>
          </label>
          <input
            value={projectForm.tone}
            onChange={(e) => handleProjectChange("tone", e.target.value)}
            className="w-full bg-input border border-line rounded p-2 text-text"
          />
        </div>
      </div>

      {/* World overview section */}
      <div className="space-y-4 pt-2 border-t border-line">
        <div className="flex items-center justify-between">
          <h2 className="text-lg">世界观</h2>
          {genreTpl && (
            <button
              type="button"
              onClick={applyTemplateDefaults}
              className="text-xs text-text-muted hover:text-text"
              title="将覆盖「力量体系」和「规则与禁忌」两栏内容"
            >
              💡 填入{genreTpl.label}默认设定
            </button>
          )}
        </div>
        {WORLD_FIELDS.map((f) => (
          <div key={f.key}>
            <label className="text-xs text-text-muted-bright block mb-1">{f.label}</label>
            <textarea
              value={(worldForm[f.key] as string) ?? ""}
              onChange={(e) => handleWorldChange(f.key, e.target.value)}
              rows={f.rows ?? 1}
              className="w-full bg-input border border-line rounded p-2 text-text"
            />
          </div>
        ))}
      </div>
    </div>
  );
}
