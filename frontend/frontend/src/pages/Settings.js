import React, { useState } from 'react';

const Settings = () => {
  const [settings, setSettings] = useState({
    default_language: 'french',
    llm_model: 'qwen3-vl:8b',
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Paramètres</h1>

      <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 space-y-6">
        <div className="border-t border-gray-200 pt-0">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Langues et LLM</h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Langue par défaut pour les bulletins
              </label>
              <select
                value={settings.default_language}
                onChange={(e) => setSettings({ ...settings, default_language: e.target.value })}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
              >
                <option value="french">Français</option>
                <option value="moore">Mooré</option>
                <option value="dioula">Dioula</option>
                <option value="fulfulde">Fulfuldé</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Modèle LLM
              </label>
              <select
                value={settings.llm_model}
                onChange={(e) => setSettings({ ...settings, llm_model: e.target.value })}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
              >
                <option value="qwen3-vl:8b">Qwen3-VL 8B</option>
                <option value="llama-2-7b">Llama 2 7B</option>
                <option value="llama-2-13b">Llama 2 13B</option>
              </select>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;

