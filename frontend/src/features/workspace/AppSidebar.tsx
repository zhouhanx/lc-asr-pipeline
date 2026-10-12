import { useState } from 'react'
import { ChevronDown, Plus, RadioTower } from 'lucide-react'

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
  const [expandedItems, setExpandedItems] = useState<Set<string>>(() => {
    const activeParent = navigationGroups
      .flatMap((group) => group.items)
      .find((item) => item.children?.some((child) => child.id === activeItem))
    return new Set(activeParent ? [activeParent.id] : [])
  })

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
                    if (item.children) {
                      const children = item.children.filter((child) => allowed.has(child.permission))
                      const childActive = children.some((child) => child.id === activeItem)
                      const expanded = expandedItems.has(item.id)
                      return (
                        <div key={item.id}>
                          <SidebarMenuItem>
                            <SidebarMenuButton
                              isActive={childActive}
                              aria-expanded={expanded}
                              className="font-head"
                              tooltip={item.label}
                              onClick={() => setExpandedItems((current) => {
                                const next = new Set(current)
                                if (next.has(item.id)) next.delete(item.id)
                                else next.add(item.id)
                                return next
                              })}
                            >
                              <Icon />
                              <span>{item.label}</span>
                              <ChevronDown className={`ml-auto transition-transform ${expanded ? 'rotate-180' : ''}`} />
                            </SidebarMenuButton>
                          </SidebarMenuItem>
                          {expanded && <div className="mt-2 grid gap-1 border-l-4 border-sidebar-border pl-3 group-data-[collapsible=icon]:hidden">{children.map((child) => {
                            const ChildIcon = child.icon
                            return <SidebarMenuItem key={child.id}><SidebarMenuButton isActive={activeItem === child.id} aria-current={activeItem === child.id ? 'page' : undefined} className="font-mono text-xs" onClick={() => onSelect(child.id)}><ChildIcon /><span>{child.label}</span>{child.badge && <Badge className="ml-auto text-[8px]" variant="outline">{child.badge}</Badge>}</SidebarMenuButton></SidebarMenuItem>
                          })}</div>}
                        </div>
                      )
                    }
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
