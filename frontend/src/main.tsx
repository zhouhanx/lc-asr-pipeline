import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App'
import { BrowserSupportGate } from './features/browser/BrowserSupportGate'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserSupportGate>
      <App />
    </BrowserSupportGate>
  </StrictMode>,
)
