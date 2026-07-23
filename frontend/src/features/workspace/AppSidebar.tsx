import { Plus, RadioTower } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import type { AuthPayload } from '@/lib/api'

import { navigationGroups } from './navigation'

type AppSidebarProps = {
  session: AuthPayload
  activeItem: string
  onSelect: (item: string) => void
}

export function AppSidebar({ session, activeItem, onSelect }: AppSidebarProps) {
  const allowed = new Set(session.permissions)

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="h-12 justify-center border-b-4 border-sidebar-border bg-primary px-2 py-0">
        <div className="flex w-full items-center gap-2">
          <div className="grid size-8 shrink-0 place-items-center border-2 border-border bg-primary font-head text-xs shadow-sm">
            LC
          </div>
          <div className="min-w-0 flex-1 group-data-[collapsible=icon]:hidden">
            <p className="truncate font-head text-xs">LC</p>
            <p className="truncate font-mono text-[9px] text-muted-foreground">VOICE & TEXT</p>
          </div>
          <SidebarTrigger className="group-data-[collapsible=icon]:hidden" />
        </div>
      </SidebarHeader>
      <SidebarContent className="gap-1 py-2">
        <SidebarGroup className="px-3 py-2">
          <Button
            variant="outline"
            className="min-h-11 w-full justify-start gap-3 group-data-[collapsible=icon]:size-10 group-data-[collapsible=icon]:p-0"
            onClick={() => onSelect('submit')}
          >
            <Plus />
            <span className="group-data-[collapsible=icon]:hidden">新建转写任务</span>
          </Button>
        </SidebarGroup>
        {navigationGroups.map((group) => {
          const items = group.items.filter((item) => allowed.has(item.permission))
          if (items.length === 0) return null
          return (
            <SidebarGroup className="px-3 py-2" key={group.label}>
              <SidebarGroupLabel className="mb-1 font-mono font-bold tracking-wider text-sidebar-foreground">
                {group.label}
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu className="gap-2">
                  {items.map((item) => {
                    const Icon = item.icon
                    return (
                      <SidebarMenuItem key={item.id}>
                        <SidebarMenuButton
                          isActive={activeItem === item.id}
                          aria-current={activeItem === item.id ? 'page' : undefined}
                          className="font-head"
                          tooltip={item.label}
                          onClick={() => onSelect(item.id)}
                        >
                          <Icon />
                          <span>{item.label}</span>
                          {item.badge && (
                            <Badge className="ml-auto text-[9px]" variant="outline">
                              {item.badge}
                            </Badge>
                          )}
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    )
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          )
        })}
      </SidebarContent>
      <SidebarFooter className="border-t-4 border-sidebar-border bg-muted p-3">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" tooltip={session.tenant.name}>
              <RadioTower />
              <div className="min-w-0 flex-1">
                <p className="truncate font-head text-xs">{session.tenant.name}</p>
                <p className="truncate font-mono text-[9px] text-muted-foreground">
                  @{session.tenant.slug}
                </p>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
