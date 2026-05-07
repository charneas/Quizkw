import { Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import Lobby from './pages/Lobby'
import Game from './pages/Game'
import MemoryGrid from './pages/MemoryGrid'
import Results from './pages/Results'
import Round2 from './pages/Round2'

function App() {
  return (
    <div className="min-h-screen bg-game-bg">
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/lobby/:code" element={<Lobby />} />
        <Route path="/game/:code" element={<Game />} />
        <Route path="/game/:code/memory-grid" element={<MemoryGrid />} />
        <Route path="/results/:code" element={<Results />} />
        <Route path="/game/:code/round2" element={<Round2 />} />
      </Routes>
    </div>
  )
}

export default App
