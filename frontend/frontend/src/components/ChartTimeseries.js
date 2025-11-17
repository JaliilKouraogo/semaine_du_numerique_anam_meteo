import React from 'react';
import ReactECharts from 'echarts-for-react';

const ChartTimeseries = ({ series = [], yLabel = 'Valeur', xLabel = 'Date', legend = true }) => {
  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
      },
    },
    legend: legend ? {
      data: series.map(s => s.name),
      bottom: 0,
    } : undefined,
    grid: {
      left: '3%',
      right: '4%',
      bottom: legend ? '15%' : '3%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: series.length > 0 ? series[0].data.map(d => d.x) : [],
      name: xLabel,
    },
    yAxis: {
      type: 'value',
      name: yLabel,
    },
    series: series.map(s => ({
      name: s.name,
      type: 'line',
      smooth: true,
      data: s.data.map(d => d.y),
      itemStyle: {
        color: s.color,
      },
    })),
  };

  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
      <ReactECharts
        option={option}
        style={{ height: '400px', width: '100%' }}
        opts={{ renderer: 'svg' }}
      />
    </div>
  );
};

export default ChartTimeseries;

