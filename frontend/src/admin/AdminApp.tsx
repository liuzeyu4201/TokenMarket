import { Route, Routes } from 'react-router-dom'
import { AdminAuthProvider } from './AdminAuthContext'
import { AdminShell } from './AdminShell'
import { Catalog } from './pages/Catalog'
import { AdminHome } from './pages/Home'
import { AdminLogin } from './pages/Login'
import { Publish } from './pages/Publish'
import { WizardPage } from './pages/Wizard'

export function AdminApp() {
  return (
    <AdminAuthProvider>
      <Routes>
        <Route element={<AdminShell />}>
          <Route index element={<AdminHome />} />
          <Route path="login" element={<AdminLogin />} />
          <Route path="ops/:kind" element={<Catalog />} />
          <Route path="ops/:kind/:id" element={<Catalog />} />
          <Route path="publish" element={<Publish />} />
          <Route path="wizards" element={<WizardPage />} />
        </Route>
      </Routes>
    </AdminAuthProvider>
  )
}

export default AdminApp
