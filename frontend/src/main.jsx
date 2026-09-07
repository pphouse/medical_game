import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { initNative } from './nativeBootstrap'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

// iOS アプリでだけ動く（ブラウザでは即座に返る）。描画を待たせたくないので
// await しない。initNative 自身が例外を外に出さない。
initNative()
