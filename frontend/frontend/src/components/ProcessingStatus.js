import React from 'react';
import { CheckCircle2, XCircle, Clock, AlertCircle } from 'lucide-react';

const ProcessingStatus = ({ jobId, steps = [] }) => {
  const getStatusIcon = (status) => {
    switch (status) {
      case 'done':
        return <CheckCircle2 className="w-5 h-5 text-success" />;
      case 'failed':
        return <XCircle className="w-5 h-5 text-danger" />;
      case 'processing':
        return <Clock className="w-5 h-5 text-primary animate-spin" />;
      default:
        return <AlertCircle className="w-5 h-5 text-gray-400" />;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'done':
        return 'text-success';
      case 'failed':
        return 'text-danger';
      case 'processing':
        return 'text-primary';
      default:
        return 'text-gray-400';
    }
  };

  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">Statut du traitement</h3>
        {jobId && (
          <span className="text-sm text-gray-500">Job ID: {jobId}</span>
        )}
      </div>
      <div className="space-y-3">
        {steps.map((step, index) => (
          <div key={index} className="flex items-start space-x-3">
            {getStatusIcon(step.status)}
            <div className="flex-1">
              <div className="flex items-center justify-between">
                <span className={`font-medium ${getStatusColor(step.status)}`}>
                  {step.name}
                </span>
                {step.timestamp && (
                  <span className="text-xs text-gray-500">{step.timestamp}</span>
                )}
              </div>
              {step.message && (
                <p className="text-sm text-gray-600 mt-1">{step.message}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ProcessingStatus;

