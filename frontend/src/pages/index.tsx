export default function Home() {
  return (
    <div style={{ padding: '2rem', textAlign: 'center' }}>
      <h1>🌤️ Clima & Negócios</h1>
      <p>Sistema funcionando perfeitamente!</p>
      <div style={{ marginTop: '2rem' }}>
        <a 
          href="http://localhost:8000/docs" 
          target="_blank"
          style={{ 
            background: '#0070f3', 
            color: 'white', 
            padding: '1rem 2rem', 
            textDecoration: 'none',
            borderRadius: '5px'
          }}
        >
          Ver API Docs
        </a>
      </div>
    </div>
  )
}