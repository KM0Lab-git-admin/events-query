import EventsList from './EventsList'
import QueryChat from './QueryChat'

function App() {
  return (
    <div className="container">
      <header className="header">
        <h1>🎉 Events Query API - Proof of Concept</h1>
        <p>Consulta eventos en lenguaje natural con IA</p>
      </header>

      <EventsList />
      
      <QueryChat />

      <footer style={{ textAlign: 'center', marginTop: '30px', padding: '20px', color: '#7f8c8d', fontSize: '13px' }}>
        <p>Events Query API v1.0 - Fase 1 MVP</p>
        <p>Backend: FastAPI + OpenAI | Frontend: React + Vite</p>
      </footer>
    </div>
  )
}

export default App
