import { useState } from 'react'
import EventsList from './EventsList'
import QueryChat from './QueryChat'
import AnalysisView from './AnalysisView'

function App() {
  const [analysisData, setAnalysisData] = useState(null)

  const handleAnalysisUpdate = (analisis) => {
    console.log('DEBUG App: Recibiendo análisis con', analisis?.length, 'eventos')
    console.log('DEBUG App: Datos completos =', analisis)
    setAnalysisData(analisis)
  }

  return (
    <div className="container">
      <header className="header">
        <h1>🎉 Events Query API - Proof of Concept</h1>
        <p>Consulta eventos en lenguaje natural con IA</p>
      </header>

      <EventsList />
      
      <QueryChat onAnalysisUpdate={handleAnalysisUpdate} />

      {analysisData && <AnalysisView analisis={analysisData} />}

      <footer style={{ textAlign: 'center', marginTop: '30px', padding: '20px', color: '#7f8c8d', fontSize: '13px' }}>
        <p>Events Query API v1.0 - Fase 1 MVP</p>
        <p>Backend: FastAPI + OpenAI | Frontend: React + Vite</p>
      </footer>
    </div>
  )
}

export default App
