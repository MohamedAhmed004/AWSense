import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { LayoutDashboard, Server, ShieldAlert, Activity, Lightbulb } from 'lucide-react'

const nav = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/resources', label: 'Resources', icon: Server },
  { to: '/security', label: 'Security', icon: ShieldAlert },
  { to: '/traffic', label: 'Traffic', icon: Activity },
  { to: '/recommendations', label: 'Recommendations', icon: Lightbulb },
]

const link = ({ isActive }) =>
  `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors ${
    isActive ? 'bg-raised text-text' : 'text-muted hover:bg-raised/60 hover:text-text'
  }`

export default function Layout() {
  const { pathname } = useLocation()
  const title = (nav.find((n) => n.to === pathname) || nav[0]).label
  const usingMock = (import.meta.env.VITE_USE_MOCK ?? 'true') !== 'false'

  return (
    <div className="min-h-screen md:flex">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-line bg-panel md:flex">
        <div className="px-5 py-5 text-lg font-semibold tracking-tight">AWSense</div>
        <nav className="flex flex-col gap-1 px-3" aria-label="Main">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'} className={link}>
              <Icon size={18} aria-hidden /> {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-line bg-panel/60 px-5 py-3 md:px-8">
          <div>
            <p className="text-base font-semibold">{title}</p>
            <p className="text-xs text-muted">Account 4821-0093-1175 · us-east-1 and eu-west-1</p>
          </div>
          <span className="rounded-full bg-raised px-3 py-1 text-xs text-muted">
            {usingMock ? 'Sample data' : 'Live data'}
          </span>
        </header>

        <nav className="flex gap-1 overflow-x-auto border-b border-line px-3 py-2 md:hidden" aria-label="Main">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'} className={link}>
              <Icon size={16} aria-hidden /> {label}
            </NavLink>
          ))}
        </nav>

        <main className="flex-1 px-5 py-6 md:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
