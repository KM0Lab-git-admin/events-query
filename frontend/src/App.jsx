import { useState } from 'react'
import EventsList from './EventsList'
import QueryChat from './QueryChat'
import AnalysisView from './AnalysisView'

function App() {
  const [analysisData, setAnalysisData] = useState(null)

  const handleAnalysisUpdate = (analisis) => {
    console.log('DEBUG App: Recibiendo análisis con', analisis?.length, 'eventos')
    setAnalysisData(analisis)
  }

  return (
    <div className="app-layout">
      <header className="header-compact">
        <h1>🎉 Events Query API</h1>
        <span className="header-badge">Proof of Concept</span>
      </header>

      <main className="main-content">
        {/* Columna izquierda: Lista de eventos */}
        <div className="column-events">
          <EventsList />
        </div>
        
        {/* Columna derecha: Chat + Análisis (sticky) */}
        <aside className="column-chat">
          <QueryChat onAnalysisUpdate={handleAnalysisUpdate} />
          {analysisData && <AnalysisView analisis={analysisData} />}
        </aside>
      </main>
    </div>
  )
}

export default App
