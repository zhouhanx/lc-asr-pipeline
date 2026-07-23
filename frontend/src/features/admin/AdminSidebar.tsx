import { AudioLines, Building2, LayoutDashboard, ListTodo, ShieldCheck } from 'lucide-react'

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarTrigger,
} from '@/components/ui/sidebar'

import type { AdminAuth, AdminView } from './types'

const menuItems = [
  { id: 'overview', label: '管理总览', icon: LayoutDashboard },
  { id: 'organizations', label: '组织和账户', icon: Building2 },
  { id: 'tasks', label: '全部转写任务', icon: ListTodo },
  { id: 'recordings', label: '全部录音文件', icon: AudioLines },
] satisfies Array<{ id: AdminView; label: string; icon: typeof LayoutDashboard }>

export function AdminSidebar({
  auth,
  activeView,
  onSelect,
}: {
  auth: AdminAuth
  activeView: AdminView
  onSelect: (view: AdminView) => void
}) {
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="h-12 justify-center border-b-4 border-sidebar-border bg-primary px-2 py-0">
        <div className="flex w-full items-center gap-2">
          <div className="grid size-8 shrink-0 place-items-center border-2 border-border bg-primary font-head text-xs shadow-sm">LC</div>
          <div className="min-w-0 flex-1 group-data-[collapsible=icon]:hidden">
            <p className="truncate font-head text-xs">超级管理平台</p>
            <p className="truncate font-mono text-[9px] text-muted-foreground">PLATFORM ADMIN</p>
          </div>
          <SidebarTrigger className="group-data-[collapsible=icon]:hidden" />
        </div>
      </SidebarHeader>
      <SidebarContent className="py-3">
        <SidebarGroup className="px-3">
          <SidebarGroupLabel className="font-mono font-bold tracking-wider text-sidebar-foreground">平台管理</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu className="gap-2">
              {menuItems.map((item) => {
                const Icon = item.icon
                return (
                  <SidebarMenuItem key={item.id}>
                    <SidebarMenuButton
                      isActive={activeView === item.id}
                      aria-current={activeView === item.id ? 'page' : undefined}
                      className="font-head"
                      tooltip={item.label}
                      onClick={() => onSelect(item.id)}
                    >
                      <Icon /><span>{item.label}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="border-t-4 border-sidebar-border bg-muted p-3">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" tooltip={auth.username}>
              <ShieldCheck />
              <div className="min-w-0 flex-1">
                <p className="truncate font-head text-xs">{auth.username}</p>
                <p className="truncate font-mono text-[9px] text-muted-foreground">SUPER ADMIN</p>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
