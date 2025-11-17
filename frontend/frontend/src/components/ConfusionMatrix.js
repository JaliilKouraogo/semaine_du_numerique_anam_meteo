import React from 'react';
import ReactECharts from 'echarts-for-react';

const ConfusionMatrix = ({ labels = [], matrix = [] }) => {
  const flattened = matrix.flat();
  const maxValue = flattened.length ? Math.max(...flattened) : 0;

  const option = {
    tooltip: {
      position: 'top',
      formatter: (params) => {
        const row = params.data[0];
        const col = params.data[1];
        return `${labels[col]} prédit comme ${labels[row]}<br/>Valeur: ${params.data[2]}`;
      },
    },
    grid: {
      height: '50%',
      top: '10%',
    },
    xAxis: {
      type: 'category',
      data: labels,
      splitArea: {
        show: true,
      },
      axisLabel: {
        rotate: 45,
      },
    },
    yAxis: {
      type: 'category',
      data: labels,
      splitArea: {
        show: true,
      },
    },
    visualMap: {
      min: 0,
      max: maxValue || 1,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: '15%',
      inRange: {
        color: ['#ffffff', '#2563EB'],
      },
    },
    series: [
      {
        name: 'Matrice de confusion',
        type: 'heatmap',
        data: matrix.flatMap((row, i) =>
          row.map((value, j) => [i, j, value])
        ),
        label: {
          show: true,
          formatter: (params) => params.data[2],
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
          },
        },
      },
    ],
  };

  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Matrice de confusion</h3>
      <ReactECharts
        option={option}
        style={{ height: '500px', width: '100%' }}
        opts={{ renderer: 'svg' }}
      />
    </div>
  );
};

export default ConfusionMatrix;

