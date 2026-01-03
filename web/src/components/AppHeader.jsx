import { NavLink } from 'react-router-dom';
import { Activity, PlayCircle, Target } from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from './ui/Badge';

function AppHeader({ scheduler, symbol }) {
  const navItems = [
    { to: '/', label: '交易回放', icon: Activity },
    { to: '/trace', label: 'Trace 线程', icon: PlayCircle },
    { to: '/focus', label: '执行焦点', icon: Target },
  ];

  return (
    <header className="fixed top-0 left-0 right-0 h-16 bg-slate-900/80 backdrop-blur-md border-b border-slate-800 z-50 px-6 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded bg-gradient-to-br from-primary to-accent flex items-center justify-center text-white shadow-lg shadow-primary/20">
            <Activity size={18} strokeWidth={2.5} />
          </div>
          <div>
            <h1 className="text-sm font-bold font-heading text-slate-100 leading-none">TradingAgents</h1>
            <p className="text-[10px] text-slate-400 font-medium tracking-wide mt-0.5">策略回放与协作面板</p>
          </div>
        </div>
      </div>

      <nav className="flex items-center bg-slate-800/50 rounded-full p-1 border border-slate-700/50">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-medium transition-all duration-200',
                isActive
                  ? 'bg-primary text-white shadow-md shadow-primary/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
              )
            }
          >
            <item.icon size={14} />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-800/50 rounded border border-slate-700/50">
          <span className="text-xs text-slate-400 font-medium">Scheduler</span>
          <div className={`w-2 h-2 rounded-full ${scheduler.running ? 'bg-success animate-pulse' : 'bg-slate-600'}`} />
        </div>
      </div>
    </header>
  );
}

export default AppHeader;
