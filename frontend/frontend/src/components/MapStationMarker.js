import React from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix pour les icônes Leaflet avec React
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

const getStationName = (station) =>
  station?.name || station?.nom || 'Station';

const MapStationMarker = ({ stations = [], onMarkerClick }) => {
  const defaultCenter = [12.371, -1.519]; // Ouagadougou
  const defaultZoom = 6;
  const burkinaBounds = [
    [9.0, -5.8],  // Sud-Ouest
    [15.5, 2.5],  // Nord-Est
  ];

  // Normaliser les stations : supporter latitude/longitude ET lat/lon
  const normalizedStations = stations.length === 0 
    ? [
        { id: 1, lat: 12.371, lon: -1.519, name: 'Ouagadougou', mae: 1.5 },
        { id: 2, lat: 11.177, lon: -4.297, name: 'Bobo-Dioulasso', mae: 2.1 },
        { id: 3, lat: 12.252, lon: -2.363, name: 'Koudougou', mae: 1.8 },
      ]
    : stations.map(station => ({
        ...station,
        name: getStationName(station),
        lat: station.lat ?? station.latitude,
        lon: station.lon ?? station.longitude,
      }));

  // Filtrer les stations avec des coordonnées valides
  const validStations = normalizedStations.filter(
    station => station.lat != null && station.lon != null && 
               !isNaN(station.lat) && !isNaN(station.lon)
  );

  return (
    <div className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 h-96">
      <MapContainer
        bounds={burkinaBounds}
        center={defaultCenter}
        zoom={defaultZoom}
        minZoom={6}
        maxZoom={9}
        maxBounds={burkinaBounds}
        maxBoundsViscosity={1}
        style={{ height: '100%', width: '100%', borderRadius: '12px' }}
        scrollWheelZoom={false}
        dragging={false}
        doubleClickZoom={false}
        zoomControl={false}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        />
        {validStations.map((station) => (
          <Marker
            key={station.id}
            position={[station.lat, station.lon]}
            eventHandlers={{
              click: () => onMarkerClick && onMarkerClick(station),
            }}
          >
            <Popup>
              <div className="p-2">
                <h4 className="font-semibold text-gray-900">{station.name}</h4>
                <p className="text-sm text-gray-600">
                  MAE: {station.mae != null ? station.mae.toFixed(2) : 
                        station.mae_tmax != null ? station.mae_tmax.toFixed(2) : 'N/A'}
                </p>
                {station.tmin_prev && (
                  <p className="text-sm text-gray-600">
                    Tmin: {station.tmin_prev}°C | Tmax: {station.tmax_prev}°C
                  </p>
                )}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
};

export default MapStationMarker;

