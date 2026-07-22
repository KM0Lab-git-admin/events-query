import { useState } from 'react'
import EventsList from './EventsList'
import NewsList from './NewsList'
import CostsView from './CostsView'

function App() {
  const [vista, setVista] = useState('eventos')

  return (
    <div className="app-layout">
      <header className="header-compact">
        <h1>🎉 Events Query API</h1>
        <span className="header-badge">Proof of Concept</span>
        <nav className="header-tabs">
          <button
            type="button"
            className={`header-tab ${vista === 'eventos' ? 'header-tab-active' : ''}`}
            onClick={() => setVista('eventos')}
          >
            Eventos
          </button>
          <button
            type="button"
            className={`header-tab ${vista === 'noticias' ? 'header-tab-active' : ''}`}
            onClick={() => setVista('noticias')}
          >
            Noticias
          </button>
          <button
            type="button"
            className={`header-tab ${vista === 'costes' ? 'header-tab-active' : ''}`}
            onClick={() => setVista('costes')}
          >
            Costes
          </button>
        </nav>
      </header>

      <main className="main-content main-content-events-only">
        {vista === 'eventos' && <EventsList />}
        {vista === 'noticias' && <NewsList />}
        {vista === 'costes' && <CostsView />}
      </main>
    </div>
  )
}

export default App
