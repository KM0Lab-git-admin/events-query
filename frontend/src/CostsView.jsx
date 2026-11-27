import { useState, useEffect } from 'react'

/** Pestaña Costes: gasto real de OpenAI por run, población y operación.
 *  Datos de /api/v1/costs/* (INGESTA_RUNS + INGESTA_COSTES, escritos por
 *  scripts/ingest_all.py al final de cada ejecución). */

const fmtUsd = (v) => `$${Number(v || 0).toFixed(4)}`
const fmtNum = (v) => Number(v || 0).toLocaleString('es-ES')
const fmtFecha = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('es-ES', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
  })
}
const fmtDuracion = (seg) => {
  if (seg == null) return '—'
  if (seg < 60) return `${seg}s`
  return `${Math.floor(seg / 60)}m ${seg % 60}s`
}

function CostsView() {
  const [runs, setRuns] = useState([])
  const [ultimoRun, setUltimoRun] = useState(null)
  const [summary, setSummary] = useState(null)
  const [dias, setDias] = useState(30)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    cargar()
  }, [dias])

  const cargar = async () => {
    try {
      setLoading(true)
      setError(null)

      const [runsRes, summaryRes] = await Promise.all([
        fetch('/api/v1/costs/runs?limit=30'),
        fetch(`/api/v1/costs/summary?dias=${dias}`)
      ])
      if (!runsRes.ok || !summaryRes.ok) {
        throw new Error('Error al cargar los costes (¿aplicado SQL/costes_delta.sql y hecho al menos un run?)')
      }
      const runsData = await runsRes.json()
      const summaryData = await summaryRes.json()
      setRuns(runsData.data || [])
      setSummary(summaryData)

      // Detalle del último run (desglose por población y operación)
      if (runsData.data?.length) {
        const detRes = await fetch(`/api/v1/costs/runs/${runsData.data[0].id_run}`)
        if (detRes.ok) {
          const det = await detRes.json()
          setUltimoRun(det.data)
        }
      } else {
        setUltimoRun(null)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="loading-spinner">Cargando costes...</div>
  if (error) return <div className="error-message">Error: {error}</div>
  if (!runs.length) {
    return (
      <div className="costs-container">
        <h2>Costes de ingesta</h2>
        <div className="no-results">
          Todavía no hay ejecuciones registradas. Ejecuta el pipeline
          (scripts/ingest_all.py) con SQL/costes_delta.sql aplicado.
        </div>
      </div>
    )
  }

  const maxCosteDia = Math.max(...(summary?.por_dia || []).map(d => d.coste_usd), 0.0001)

  return (
    <div className="costs-container">
      <div className="costs-header-row">
        <h2>Costes de ingesta</h2>
        <select value={dias} onChange={(e) => setDias(Number(e.target.value))}>
          <option value={7}>Últimos 7 días</option>
          <option value={30}>Últimos 30 días</option>
          <option value={90}>Últimos 90 días</option>
        </select>
      </div>

      {/* ===== Último run ===== */}
      {ultimoRun && (
        <section className="costs-section">
          <h3>
            Último run · {fmtFecha(ultimoRun.inicio)} · {ultimoRun.target} ·{' '}
            <code>{ultimoRun.modelo}</code>
            {ultimoRun.parametros ? <span className="costs-params"> ({ultimoRun.parametros})</span> : null}
          </h3>

          <div className="costs-cards">
            <div className="cost-card cost-card-main">
              <span className="cost-card-value">{fmtUsd(ultimoRun.coste_usd)}</span>
              <span className="cost-card-label">Gasto OpenAI</span>
            </div>
            <div className="cost-card">
              <span className="cost-card-value">{fmtNum(ultimoRun.llamadas)}</span>
              <span className="cost-card-label">Llamadas LLM</span>
            </div>
            <div className="cost-card">
              <span className="cost-card-value">{fmtNum(ultimoRun.tokens_in + ultimoRun.tokens_cached)}</span>
              <span className="cost-card-label">Tokens entrada{ultimoRun.tokens_cached ? ` (${fmtNum(ultimoRun.tokens_cached)} cacheados)` : ''}</span>
            </div>
            <div className="cost-card">
              <span className="cost-card-value">{fmtNum(ultimoRun.tokens_out)}</span>
              <span className="cost-card-label">Tokens salida</span>
            </div>
            <div className="cost-card">
              <span className="cost-card-value">{ultimoRun.eventos} / {ultimoRun.noticias}</span>
              <span className="cost-card-label">Eventos / Noticias</span>
            </div>
            <div className="cost-card">
              <span className="cost-card-value">{fmtDuracion(ultimoRun.duracion_seg)}</span>
              <span className="cost-card-label">Duración</span>
            </div>
            <div className="cost-card">
              <span className="cost-card-value">
                {ultimoRun.targets_ok} / {ultimoRun.targets_skip} / {ultimoRun.targets_error}
              </span>
              <span className="cost-card-label">Targets OK / skip / error</span>
            </div>
          </div>

          <div className="costs-tables">
            <div className="costs-table-wrap">
              <h4>Por población</h4>
              <table className="costs-table">
                <thead>
                  <tr><th>Población</th><th>Llam.</th><th>Tok. in</th><th>Tok. out</th><th>Coste</th></tr>
                </thead>
                <tbody>
                  {(ultimoRun.por_poblacion || []).map((p) => (
                    <tr key={p.poblacion}>
                      <td>{p.poblacion}</td>
                      <td>{fmtNum(p.llamadas)}</td>
                      <td>{fmtNum(p.tokens_in + p.tokens_cached)}</td>
                      <td>{fmtNum(p.tokens_out)}</td>
                      <td className="costs-money">{fmtUsd(p.coste_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="costs-table-wrap">
              <h4>Por operación</h4>
              <table className="costs-table">
                <thead>
                  <tr><th>Operación</th><th>Llam.</th><th>Tok. in</th><th>Tok. out</th><th>Coste</th></tr>
                </thead>
                <tbody>
                  {(ultimoRun.por_operacion || []).map((o) => (
                    <tr key={o.operacion}>
                      <td>{o.operacion}</td>
                      <td>{fmtNum(o.llamadas)}</td>
                      <td>{fmtNum(o.tokens_in + o.tokens_cached)}</td>
                      <td>{fmtNum(o.tokens_out)}</td>
                      <td className="costs-money">{fmtUsd(o.coste_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {/* ===== Periodo ===== */}
      {summary && (
        <section className="costs-section">
          <h3>
            Acumulado {dias} días · {summary.totales.runs} runs ·{' '}
            <strong>{fmtUsd(summary.totales.coste_usd)}</strong> ·{' '}
            {summary.totales.eventos} eventos · {summary.totales.noticias} noticias
          </h3>

          <div className="costs-tables">
            <div className="costs-table-wrap">
              <h4>Por población (periodo)</h4>
              <table className="costs-table">
                <thead>
                  <tr><th>Población</th><th>Llam.</th><th>Tok. in</th><th>Tok. out</th><th>Coste</th></tr>
                </thead>
                <tbody>
                  {(summary.por_poblacion || []).map((p) => (
                    <tr key={p.poblacion}>
                      <td>{p.poblacion}</td>
                      <td>{fmtNum(p.llamadas)}</td>
                      <td>{fmtNum(p.tokens_in + p.tokens_cached)}</td>
                      <td>{fmtNum(p.tokens_out)}</td>
                      <td className="costs-money">{fmtUsd(p.coste_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="costs-table-wrap">
              <h4>Gasto por día</h4>
              <div className="costs-bars">
                {(summary.por_dia || []).map((d) => (
                  <div key={d.fecha} className="costs-bar-row" title={`${d.runs} runs · ${d.eventos} eventos · ${d.noticias} noticias`}>
                    <span className="costs-bar-fecha">{d.fecha.slice(5)}</span>
                    <div className="costs-bar-track">
                      <div
                        className="costs-bar-fill"
                        style={{ width: `${Math.max(2, (d.coste_usd / maxCosteDia) * 100)}%` }}
                      />
                    </div>
                    <span className="costs-bar-valor">{fmtUsd(d.coste_usd)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* ===== Histórico de runs ===== */}
      <section className="costs-section">
        <h3>Histórico de runs</h3>
        <table className="costs-table costs-table-full">
          <thead>
            <tr>
              <th>Fecha</th><th>Target</th><th>Modelo</th><th>Parámetros</th>
              <th>Llam.</th><th>Eventos</th><th>Noticias</th>
              <th>Targets OK/skip/err</th><th>Duración</th><th>Coste</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id_run}>
                <td>{fmtFecha(r.inicio)}</td>
                <td>{r.target}</td>
                <td><code>{r.modelo}</code></td>
                <td className="costs-params">{r.parametros || '—'}</td>
                <td>{fmtNum(r.llamadas)}</td>
                <td>{r.eventos}</td>
                <td>{r.noticias}</td>
                <td>{r.targets_ok}/{r.targets_skip}/{r.targets_error}</td>
                <td>{fmtDuracion(r.duracion_seg)}</td>
                <td className="costs-money">{fmtUsd(r.coste_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

export default CostsView
