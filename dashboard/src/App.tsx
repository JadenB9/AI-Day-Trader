import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Positions from './pages/Positions'
import Strategies from './pages/Strategies'
import Settings from './pages/Settings'
import Analytics from './pages/Analytics'
import Activity from './pages/Activity'

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/positions" element={<Positions />} />
          <Route path="/strategies" element={<Strategies />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/activity" element={<Activity />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
