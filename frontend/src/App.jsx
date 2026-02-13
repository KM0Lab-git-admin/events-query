import { useState } from 'react'
import EventsList from './EventsList'
import QueryChat from './QueryChat'
import AnalysisView from './AnalysisView'

function App() {
  const [analysisData, setAnalysisData] = useState(null)
  const [activeTab, setActiveTab] = useState('eventos')

  const handleAnalysisUpdate = (analisis) => {
    console.log('DEBUG App: Recibiendo análisis con', analisis?.length, 'eventos')
    setAnalysisData(analisis)
  }

  return (
    <div className="app-layout">
      <header className="header-compact">
        <h1>🎉 Events Query API</h1>
        <span className="header-badge">Proof of Concept</span>
        <nav className="header-tabs" aria-label="Secciones">
          <button
            type="button"
            className={`header-tab ${activeTab === 'eventos' ? 'header-tab-active' : ''}`}
            onClick={() => setActiveTab('eventos')}
          >
            Eventos
          </button>
          <button
            type="button"
            className={`header-tab ${activeTab === 'consultas' ? 'header-tab-active' : ''}`}
            onClick={() => setActiveTab('consultas')}
          >
            Consultas
          </button>
        </nav>
      </header>

      <main className="main-content">
        <div
          className={`column-events column-events-full ${activeTab !== 'eventos' ? 'tab-panel-hidden' : ''}`}
          aria-hidden={activeTab !== 'eventos'}
        >
          <EventsList />
        </div>
        <aside
          className={`column-chat column-chat-full ${activeTab !== 'consultas' ? 'tab-panel-hidden' : ''}`}
          aria-hidden={activeTab !== 'consultas'}
        >
          <QueryChat onAnalysisUpdate={handleAnalysisUpdate} />
          {analysisData && <AnalysisView analisis={analysisData} />}
        </aside>
      </main>
    </div>
  )
}

export default App
