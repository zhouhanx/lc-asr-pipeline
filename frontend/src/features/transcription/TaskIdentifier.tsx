import { useState } from 'react'
import { Check, Copy } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function TaskIdentifier({
  taskId,
  className,
}: {
  taskId: string
  className?: string
}) {
  const [copied, setCopied] = useState(false)

  return (
    <div className={cn('flex min-w-0 items-center gap-2 border-2 border-border bg-background px-3 py-2 font-mono text-xs', className)}>
      <span className="shrink-0 text-muted-foreground">任务 ID</span>
      <code className="min-w-0 flex-1 break-all font-bold">{taskId}</code>
      <Button
        aria-label={`复制任务 ID ${taskId}`}
        className="shrink-0"
        size="icon-sm"
        variant="ghost"
        onClick={async () => {
          await navigator.clipboard.writeText(taskId)
          setCopied(true)
        }}
      >
        {copied ? <Check /> : <Copy />}
      </Button>
    </div>
  )
}
