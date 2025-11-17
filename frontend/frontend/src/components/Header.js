import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu } from 'lucide-react';

const Header = ({ onMenuClick }) => {
  const navigate = useNavigate();

  return (
    <header className="bg-white border-b border-gray-200 px-6 py-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <button
            onClick={onMenuClick}
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
            aria-label="Toggle menu"
          >
            <Menu className="w-6 h-6 text-gray-700" />
          </button>
          <div className="flex items-center cursor-pointer" onClick={() => navigate('/')}>
            <img
              src="/logo_anam.png"
              alt="ANAM Burkina"
              className="h-16 w-auto object-contain"
              loading="lazy"
            />
          </div>
        </div>
        
      </div>
    </header>
  );
};

export default Header;

