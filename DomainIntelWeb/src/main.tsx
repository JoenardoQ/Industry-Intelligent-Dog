import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles.css'

const sessionMatch = location.hash.match(/(?:^|[&#])session=([^&]+)/)
if (sessionMatch) {
  sessionStorage.setItem('intdog.session', decodeURIComponent(sessionMatch[1]))
  history.replaceState(null, '', `${location.pathname}${location.search}#/overview`)
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>,
)
