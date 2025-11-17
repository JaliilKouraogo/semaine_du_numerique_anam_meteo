import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FileText,
  MapPin,
  BarChart3,
  FileCheck,
  Settings,
} from 'lucide-react';

const Sidebar = ({ isOpen, onToggle }) => {
  const menuItems = [
    { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/bulletin', icon: FileText, label: 'Files' },
    { path: '/stations', icon: MapPin, label: 'Stations' },
    { path: '/evaluation', icon: BarChart3, label: 'Évaluations' },
    { path: '/logs', icon: FileCheck, label: 'Logs' },
    { path: '/settings', icon: Settings, label: 'Paramètres' },
  ];

  return (
    <>
      <aside
        className={`bg-white border-r border-gray-200 transition-all duration-300 h-full flex-shrink-0 ${
          isOpen ? 'w-56' : 'w-0 overflow-hidden'
        }`}
      >
        <nav className="p-4 space-y-2 h-full overflow-y-auto">
          {menuItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-primary text-white'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`
                }
              >
                <Icon className="w-5 h-5" />
                <span className="font-medium">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </aside>
    </>
  );
};

export default Sidebar;

