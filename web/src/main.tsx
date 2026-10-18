import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import Home from './Home.tsx'

function Root() {
  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    const on = () => setHash(window.location.hash)
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  const inApp = hash.startsWith('#/app')
  useEffect(() => {
    document.body.classList.toggle('in-app', inApp)
    window.scrollTo(0, 0)
  }, [inApp])
  return inApp ? <App /> : <Home />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
