import React from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

const KPICard = ({ title, value, delta24h, sparkline, unit = '' }) => {
  const isPositive = delta24h > 0;
  const isNegative = delta24h < 0;
  const isNeutral = delta24h === 0;

  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
      <div className="flex items-start justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-600">{title}</h3>
        {sparkline && (
          <div className="w-16 h-8 text-primary opacity-50">
            {sparkline}
          </div>
        )}
      </div>
      <div className="flex items-baseline space-x-3">
        <span className="text-3xl font-bold text-gray-900">
          {value}
          {unit && <span className="text-lg text-gray-500 ml-1">{unit}</span>}
        </span>
        {delta24h !== null && (
          <div
            className={`flex items-center space-x-1 px-2 py-1 rounded-full text-xs font-medium ${
              isPositive
                ? 'bg-green-100 text-green-700'
                : isNegative
                ? 'bg-red-100 text-red-700'
                : 'bg-gray-100 text-gray-700'
            }`}
          >
            {isPositive && <TrendingUp className="w-3 h-3" />}
            {isNegative && <TrendingDown className="w-3 h-3" />}
            {isNeutral && <Minus className="w-3 h-3" />}
            <span>{Math.abs(delta24h)}%</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default KPICard;

