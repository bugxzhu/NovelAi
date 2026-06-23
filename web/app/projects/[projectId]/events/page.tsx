"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { useEvents } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import { Button } from "@/components/ui/Button";
import { EventForm } from "@/components/entities/EventForm";
import { EventList } from "@/components/entities/EventList";
import { ForeshadowMultiselect } from "@/components/entities/ForeshadowMultiselect";
import type { EventFilter } from "@/lib/types";

export default function EventsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const [filter, setFilter] = useState<EventFilter>("all");
  const { data: events = [], isLoading } = useEvents(pid, { filter });
  // Use a separate non-filtered query for ForeshadowMultiselect's "all events" dropdown
  const { data: allEvents = [] } = useEvents(pid, { filter: "all" });
  const [mode, setMode] = useState<"list" | "create">("list");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = (allEvents ?? []).find((e) => e.id === selectedId);

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel
          title="事件"
          action={
            <Button
              variant="ghost"
              onClick={() => {
                setMode("create");
                setSelectedId(null);
              }}
            >
              + 新建
            </Button>
          }
        >
          {isLoading ? (
            <p className="text-xs text-text-muted p-2">加载中...</p>
          ) : (
            <EventList
              events={events}
              selectedId={selectedId}
              onSelect={(id) => {
                setMode("list");
                setSelectedId(id);
              }}
              onFilterChange={setFilter}
            />
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto">
          {mode === "create" ? (
            <EventForm projectId={pid} chapterId={0} />
          ) : selected ? (
            <div>
              <EventForm
                projectId={pid}
                chapterId={selected.chapter_id}
                event={selected}
              />
              <ForeshadowMultiselect event={selected} allEvents={allEvents} />
            </div>
          ) : (
            <div className="p-4 text-text-muted">
              还没有事件。完成一章后 AI 会自动抽取关键事件，或点击左侧&quot;+ 新建&quot;手动添加。
            </div>
          )}
        </div>
      }
    />
  );
}
