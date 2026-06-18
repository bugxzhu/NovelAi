import { WorkspaceShell } from "@/components/layout/WorkspaceShell";

export default async function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <WorkspaceShell projectId={Number(projectId)}>{children}</WorkspaceShell>;
}
