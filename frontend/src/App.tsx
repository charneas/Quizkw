import { Routes, Route } from 'react-router-dom'
import ThemeToggle from './components/ThemeToggle'
import Home from './pages/Home'
import Lobby from './pages/Lobby'
import Game from './pages/Game'
import HostGame from './pages/HostGame'
import TeamScreen from './pages/TeamScreen'
import MemoryGrid from './pages/MemoryGrid'
import Results from './pages/Results'
import Round2 from './pages/Round2'
import Admin from './pages/Admin'
import Propositions from './pages/Propositions'
import AdminLogin from './pages/AdminLogin'
import AdminPropositions from './pages/AdminPropositions'
import AdminPropositionEdit from './pages/AdminPropositionEdit'
import AdminPropositionsRejected from './pages/AdminPropositionsRejected'
import AdminStats from './pages/AdminStats'
import AdminThemes from './pages/AdminThemes'
import AdminQuestions from './pages/AdminQuestions'
import AdminContentGeneration from './pages/AdminContentGeneration'

function App() {
  return (
    <div className="min-h-screen bg-bg">
      <ThemeToggle />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/lobby/:code" element={<Lobby />} />
        <Route path="/game/:code" element={<Game />} />
        <Route path="/game/:code/host" element={<HostGame />} />
        <Route path="/team/:code/:teamId" element={<TeamScreen />} />
        <Route path="/game/:code/memory-grid" element={<MemoryGrid />} />
        <Route path="/results/:code" element={<Results />} />
        <Route path="/game/:code/round2" element={<Round2 />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/admin/login" element={<AdminLogin />} />
        <Route path="/admin/themes" element={<AdminThemes />} />
        <Route path="/admin/questions" element={<AdminQuestions />} />
        <Route path="/admin/content/generate" element={<AdminContentGeneration />} />
        <Route path="/admin/propositions" element={<AdminPropositions />} />
        <Route path="/admin/propositions/rejected" element={<AdminPropositionsRejected />} />
        <Route path="/admin/propositions/:id/edit" element={<AdminPropositionEdit />} />
        <Route path="/admin/stats" element={<AdminStats />} />
        <Route path="/proposer" element={<Propositions />} />
      </Routes>
    </div>
  )
}

export default App
