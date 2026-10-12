import type { PropsWithChildren, ReactNode } from 'react'

import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'

type AuthShellProps = PropsWithChildren<{
  title: string
  description: string
  eyebrow?: string
  footer?: ReactNode
}>

export function AuthShell({
  title,
  description,
  eyebrow = 'SECURE TENANT ACCESS',
  footer,
  children,
}: AuthShellProps) {
  return (
    <main className="pixel-grid flex min-h-screen flex-col items-center justify-center px-4 py-12 sm:px-6">
      <Card className="w-full max-w-2xl bg-card [&_[data-slot=button]]:min-h-11 [&_[data-slot=input]]:h-11 [&_[data-slot=input]]:text-base">
        <CardHeader className="border-b-2 border-border px-6 pb-6 pt-6 sm:px-8 sm:pt-8">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="grid size-14 place-items-center border-2 border-border bg-primary font-head text-xl shadow-sm">
                LC
              </div>
              <div>
                <p className="font-mono text-xs tracking-[0.2em]">LC</p>
                <p className="font-head text-base">VOICE & TEXT</p>
              </div>
            </div>
            <span className="border-2 border-border bg-accent px-2 py-1 font-mono text-[10px] shadow-sm">
              CN
            </span>
          </div>
        </CardHeader>
        <CardHeader className="px-6 pt-7 sm:px-8">
          <p className="font-mono text-xs tracking-[0.2em] text-muted-foreground">{eyebrow}</p>
          <h1 className="font-head text-4xl font-medium uppercase">{title}</h1>
          <CardDescription className="text-base leading-7">{description}</CardDescription>
        </CardHeader>
        <CardContent className="px-6 pb-8 sm:px-8">{children}</CardContent>
        {footer && <div className="border-t-2 border-border bg-muted px-6 py-4 sm:px-8">{footer}</div>}
      </Card>
      <p className="mt-6 font-mono text-[10px] tracking-[0.14em] text-muted-foreground">
        LC · TENANT SAFE MODE
      </p>
    </main>
  )
}
