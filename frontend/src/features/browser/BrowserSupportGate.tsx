import type { PropsWithChildren } from 'react'

import { detectSupportedBrowser } from './browser-policy'

export function BrowserSupportGate({ children }: PropsWithChildren) {
  if (detectSupportedBrowser() !== null) return children
  return (
    <main className="pixel-grid flex min-h-screen items-center justify-center px-5 py-12">
      <section
        className="w-full max-w-xl border-2 border-border bg-card p-8 shadow-md"
        aria-labelledby="unsupported-browser-title"
      >
        <p className="font-mono text-xs tracking-[0.18em] text-muted-foreground">
          BROWSER NOT SUPPORTED
        </p>
        <h1
          id="unsupported-browser-title"
          className="mt-3 font-head text-4xl uppercase"
        >
          请使用 Chrome 或 Edge
        </h1>
        <p className="mt-5 leading-7 text-muted-foreground">
          LC 仅适配桌面版 Google Chrome 和 Microsoft Edge。当前浏览器不会加载登录状态，也不会向业务 API 发送请求。
        </p>
      </section>
    </main>
  )
}
