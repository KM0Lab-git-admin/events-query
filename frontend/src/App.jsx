import EventsList from './EventsList'

function App() {
  return (
    <div className="app-layout">
      <header className="header-compact">
        <h1>🎉 Events Query API</h1>
        <span className="header-badge">Proof of Concept</span>
      </header>

      <main className="main-content main-content-events-only">
        <EventsList />
      </main>
    </div>
  )
}

export default App
