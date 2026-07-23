import { useState } from 'react'
import { Bell, ChevronDown, CircleHelp, KeyRound, LogOut, ShieldCheck } from 'lucide-react'

import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { SidebarTrigger } from '@/components/ui/sidebar'
import type { AuthPayload } from '@/lib/api'

import { PasswordChangeSheet } from '../auth/PasswordChangeSheet'

type WorkspaceHeaderProps = {
  session: AuthPayload
  title: string
  onLogout: () => Promise<void>
}

export function WorkspaceHeader({ session, title, onLogout }: WorkspaceHeaderProps) {
  const initials = session.user.display_name.slice(0, 2).toUpperCase()
  const [passwordOpen, setPasswordOpen] = useState(false)

  return (
    <header className="sticky top-0 z-20 flex h-12 items-center justify-between border-b-2 border-border bg-card px-3">
      <div className="flex min-w-0 items-center gap-3">
        <SidebarTrigger />
        <div className="h-5 w-0.5 bg-border" />
        <div className="min-w-0">
          <p className="truncate font-head text-sm">{title}</p>
          <p className="hidden font-mono text-[9px] text-muted-foreground sm:block">
            {session.tenant.slug} / {session.permissions.length} PERMISSIONS
          </p>
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        <Button variant="ghost" size="icon-sm" aria-label="帮助">
          <CircleHelp />
        </Button>
        <Button variant="ghost" size="icon-sm" aria-label="通知">
          <Bell />
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-9 gap-2 px-1.5">
              <Avatar size="sm">
                <AvatarFallback className="bg-primary text-foreground">{initials}</AvatarFallback>
              </Avatar>
              <span className="hidden max-w-28 truncate text-xs sm:block">
                {session.user.display_name}
              </span>
              <ChevronDown className="size-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-64" align="end">
            <DropdownMenuLabel>
              <p className="font-head text-xs">{session.user.display_name}</p>
              <p className="mt-1 break-all font-mono text-[10px] font-normal text-muted-foreground">
                {session.user.email}
              </p>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled>
              <ShieldCheck /> 权限档案
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setPasswordOpen(true)}>
              <KeyRound /> 修改密码
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={() => void onLogout()}>
              <LogOut /> 退出登录
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <PasswordChangeSheet
        open={passwordOpen}
        onOpenChange={setPasswordOpen}
        endpoint="/auth/change-password"
        token={session.access_token}
        onChanged={onLogout}
      />
    </header>
  )
}
