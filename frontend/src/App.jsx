import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import Overview from './pages/Overview.jsx'
import Resources from './pages/Resources.jsx'
import Security from './pages/Security.jsx'
import Traffic from './pages/Traffic.jsx'
import Recommendations from './pages/Recommendations.jsx'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="resources" element={<Resources />} />
        <Route path="security" element={<Security />} />
        <Route path="traffic" element={<Traffic />} />
        <Route path="recommendations" element={<Recommendations />} />
        <Route path="*" element={<Overview />} />
      </Route>
    </Routes>
  )
}
