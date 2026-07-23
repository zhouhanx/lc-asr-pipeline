import { useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useAuth } from '@/features/auth/useAuth'
import { ModelPanel } from '@/features/models/ModelPanel'
import { FileHistoryPanel } from '@/features/transcription/FileHistoryPanel'
import { PublicTaskPanel } from '@/features/transcription/PublicTaskPanel'
import { SubmissionPanel } from '@/features/transcription/SubmissionPanel'
import { TaskDetailPanel } from '@/features/transcription/TaskDetailPanel'
import { TaskListPanel } from '@/features/transcription/TaskListPanel'
import type { AuthPayload } from '@/lib/api'

import { AppSidebar } from './AppSidebar'
import { allNavigationItems } from './navigation'
import { OverviewPanel } from './OverviewPanel'
import { WorkspaceHeader } from './WorkspaceHeader'

export function WorkspacePage() {
  const { session, logout } = useAuth()
  if (!session) return null

  return <AuthenticatedWorkspace session={session} onLogout={logout} />
}

type AuthenticatedWorkspaceProps = {
  session: AuthPayload
  onLogout: () => Promise<void>
}

function AuthenticatedWorkspace({ session, onLogout }: AuthenticatedWorkspaceProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const allowedItems = useMemo(
    () => allNavigationItems.filter((item) => session.permissions.includes(item.permission)),
    [session.permissions],
  )
  const pathParts = location.pathname.split('/').filter(Boolean)
  const jobId = pathParts[1] === 'tasks' && pathParts[2] ? pathParts[2] : null
  const requestedItem = jobId ? 'tasks' : (pathParts[1] ?? 'overview')
  const activeItem = allowedItems.some((item) => item.id === requestedItem)
    ? requestedItem
    : (allowedItems[0]?.id ?? 'overview')
  const selected = allowedItems.find((item) => item.id === activeItem) ?? allowedItems[0]

  const selectItem = (item: string) => {
    navigate(`/workspace/${item}`)
  }

  return (
    <TooltipProvider delayDuration={100}>
      <SidebarProvider>
        <AppSidebar session={session} activeItem={activeItem} onSelect={selectItem} />
        <SidebarInset>
          <WorkspaceHeader session={session} title={jobId ? '任务详情' : (selected?.label ?? '工作台')} onLogout={onLogout} />
          <main className="pixel-grid flex-1 overflow-y-auto p-4 sm:p-6">
            {activeItem === 'overview' ? (
              <OverviewPanel session={session} onNavigate={selectItem} />
            ) : activeItem === 'submit' ? (
              <SubmissionPanel session={session} onOpenTasks={() => navigate('/workspace/tasks')} onOpenHistory={() => navigate('/workspace/history')} />
            ) : activeItem === 'tasks' && jobId ? (
              <TaskDetailPanel session={session} jobId={jobId} onBack={() => navigate('/workspace/tasks')} />
            ) : activeItem === 'tasks' ? (
              <TaskListPanel session={session} onOpenTask={(id) => navigate(`/workspace/tasks/${id}`)} />
            ) : activeItem === 'history' ? (
              <FileHistoryPanel session={session} onOpenTask={(id) => navigate(`/workspace/tasks/${id}`)} />
            ) : activeItem === 'public-tasks' ? (
              <PublicTaskPanel session={session} />
            ) : activeItem === 'models' ? (
              <ModelPanel session={session} />
            ) : (
              <Card className="mx-auto max-w-5xl">
                <CardHeader>
                  <CardTitle className="font-head text-3xl">{selected?.label}</CardTitle>
                  <CardDescription>{selected?.description}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid min-h-64 place-items-center border-2 border-dashed border-border bg-muted/40 p-8 text-center">
                    <div>
                      <p className="font-head text-lg">MODULE RESERVED</p>
                      <p className="mt-2 max-w-md font-mono text-xs leading-5 text-muted-foreground">
                        页面入口已按权限开放；对应业务 API 将在 ASR 功能阶段实现。
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </main>
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  )
}
