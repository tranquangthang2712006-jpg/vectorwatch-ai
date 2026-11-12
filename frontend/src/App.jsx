import { Navigate, Route, Routes } from 'react-router-dom'
import { AppProvider, ToastProvider, useApp } from './lib/context.jsx'
import Layout from './components/Layout.jsx'
import { ErrorState, Loading } from './components/ui.jsx'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import MapPage from './pages/MapPage.jsx'
import DataPage from './pages/DataPage.jsx'
import AnalysisPage from './pages/AnalysisPage.jsx'
import AgentCenter from './pages/AgentCenter.jsx'
import AlertsPage from './pages/AlertsPage.jsx'
import ReportsPage from './pages/ReportsPage.jsx'
import SettingsPage from './pages/SettingsPage.jsx'

function Shell() {
  const { user, meta, booting, bootError, reloadSession } = useApp()
  if (booting) return <Loading label="Đang khởi động VectorWatch AI…" className="h-full" />
  if (bootError) return <div className="flex h-full items-center justify-center"><ErrorState message={bootError} onRetry={reloadSession} /></div>
  if (!user || !meta) return <Login />
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="map" element={<MapPage />} />
        <Route path="analysis" element={<AnalysisPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="agent" element={<AgentCenter />} />
        <Route path="data" element={<DataPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <AppProvider>
        <Shell />
      </AppProvider>
    </ToastProvider>
  )
}
