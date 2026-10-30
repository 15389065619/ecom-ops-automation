(function () {
  var data = window.DASHBOARD_DATA;
  if (!data) return;

  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  function money(v) {
    return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function pct(v) {
    return (Number(v) * 100).toFixed(2) + '%';
  }
  function int(v) {
    return Number(v).toLocaleString('zh-CN');
  }
  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  var ov = data.overview;
  var period = data.period;

  // ---------- 头部与 KPI ----------
  setText('period-line', '统计区间 ' + period.start + ' ~ ' + period.end + '（' + period.days + ' 天）');
  setText('generated-at', data.generated_at);
  setText('kpi-revenue', money(ov.revenue));
  setText('kpi-revenue-foot', '日均 ' + money(ov.revenue / period.days) + ' 元');
  setText('kpi-profit', money(ov.net_profit));
  setText('kpi-profit-foot', '日均 ' + money(ov.net_profit / period.days) + ' 元');
  setText('kpi-margin', pct(ov.margin));
  setText('kpi-return', pct(ov.return_rate));
  setText('kpi-return-foot', '退款 ' + int(ov.refund_orders) + ' 单 · 金额 ' + money(ov.refunds));
  setText('kpi-orders', int(ov.orders));
  setText('kpi-units', int(ov.units));
  setText('kpi-fees', money(ov.amazon_fees));
  setText('kpi-cogs', money(ov.cogs));
  setText('kpi-ads', money(ov.ad_spend));
  setText('kpi-refunds', money(ov.refunds));
  setText('kpi-skus', int(ov.sku_count));

  // ---------- 表格 ----------
  function row(cells, numericFrom) {
    return '<tr>' + cells.map(function (cell, i) {
      if (i < (numericFrom || 0)) return '<td>' + cell + '</td>';
      var v = cell.value !== undefined ? cell : { value: cell };
      var cls = 'num' + (v.cls ? ' ' + v.cls : '');
      return '<td class="' + cls + '">' + v.value + '</td>';
    }).join('') + '</tr>';
  }

  var marketBody = document.getElementById('market-body');
  marketBody.innerHTML = data.by_marketplace.map(function (m) {
    return row([
      '<strong>' + m.marketplace + '</strong>',
      int(m.orders),
      int(m.units),
      money(m.revenue),
      { value: money(m.net_profit), cls: m.net_profit < 0 ? 'neg' : 'pos' },
      pct(m.margin),
      money(m.ad_spend),
      pct(m.return_rate)
    ], 1);
  }).join('');

  var skuBody = document.getElementById('sku-body');
  skuBody.innerHTML = data.by_sku.map(function (s) {
    return row([
      '<strong>' + s.sku + '</strong>',
      int(s.units),
      money(s.revenue),
      { value: money(s.net_profit), cls: s.net_profit < 0 ? 'neg' : 'pos' },
      { value: pct(s.margin), cls: s.margin < 0.08 ? 'neg' : '' },
      money(s.ad_spend),
      pct(s.return_rate)
    ], 1);
  }).join('');

  var alertBody = document.getElementById('alert-body');
  alertBody.innerHTML = data.alerts.map(function (a) {
    return '<tr><td><span class="badge ' + a.level.toLowerCase() + '">' + a.level + '</span></td>' +
      '<td>' + a.type + '</td><td><strong>' + a.target + '</strong></td><td>' + a.message + '</td></tr>';
  }).join('');
  setText('alert-count', data.alerts.length);

  // ---------- 图表 ----------
  var grid = { left: 64, right: 28, top: 26, bottom: 44 };

  var chartDaily = echarts.init(document.getElementById('chart-daily'), null, { renderer: 'svg' });
  var days = data.daily.map(function (d) { return d.order_date.slice(5); });
  chartDaily.setOption({
    animation: false,
    grid: grid,
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      axisPointer: { type: 'shadow' },
      valueFormatter: function (v) { return money(v); }
    },
    legend: { right: 10, top: 0, itemWidth: 12, itemHeight: 8, textStyle: { color: muted, fontSize: 12 } },
    xAxis: {
      type: 'category',
      data: days,
      axisLine: { lineStyle: { color: rule } },
      axisTick: { show: false },
      axisLabel: { color: muted, fontSize: 11, interval: 2 }
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      axisLabel: { color: muted, fontSize: 11 }
    },
    series: [
      {
        name: '销售额',
        type: 'bar',
        data: data.daily.map(function (d) { return d.revenue; }),
        barMaxWidth: 18,
        itemStyle: { color: accent + '59', borderRadius: [2, 2, 0, 0] }
      },
      {
        name: '净利',
        type: 'line',
        data: data.daily.map(function (d) { return d.net_profit; }),
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { width: 2, color: ink },
        itemStyle: { color: ink }
      }
    ]
  });
  window.addEventListener('resize', function () { chartDaily.resize(); });

  var skus = data.by_sku.slice().sort(function (a, b) { return a.net_profit - b.net_profit; });
  var chartSku = echarts.init(document.getElementById('chart-sku'), null, { renderer: 'svg' });
  chartSku.setOption({
    animation: false,
    grid: { left: 92, right: 74, top: 14, bottom: 22 },
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      axisPointer: { type: 'shadow' },
      valueFormatter: function (v) { return money(v); }
    },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      axisLabel: { color: muted, fontSize: 11 }
    },
    yAxis: {
      type: 'category',
      data: skus.map(function (s) { return s.sku; }),
      axisLine: { lineStyle: { color: rule } },
      axisTick: { show: false },
      axisLabel: { color: ink, fontSize: 11 }
    },
    series: [{
      type: 'bar',
      data: skus.map(function (s) {
        return {
          value: s.net_profit,
          itemStyle: { color: s.net_profit >= 0 ? accent : accent2, borderRadius: 2 }
        };
      }),
      barWidth: 14,
      label: {
        show: true,
        position: 'right',
        color: muted,
        fontSize: 11,
        formatter: function (p) { return money(p.value); }
      }
    }]
  });
  window.addEventListener('resize', function () { chartSku.resize(); });

  var chartMarket = echarts.init(document.getElementById('chart-market'), null, { renderer: 'svg' });
  chartMarket.setOption({
    animation: false,
    tooltip: {
      trigger: 'item',
      appendToBody: true,
      formatter: function (p) { return p.name + '<br/>销售额 ' + money(p.value) + '（' + p.percent + '%）'; }
    },
    legend: { bottom: 4, itemWidth: 10, itemHeight: 10, textStyle: { color: muted, fontSize: 12 } },
    series: [{
      type: 'pie',
      radius: ['50%', '74%'],
      center: ['50%', '46%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: bg2, borderWidth: 3 },
      label: { show: false },
      emphasis: { label: { show: false } },
      data: data.by_marketplace.map(function (m, i) {
        return {
          name: m.marketplace,
          value: m.revenue,
          itemStyle: { color: [accent, ink, muted][i % 3] }
        };
      })
    }]
  });
  window.addEventListener('resize', function () { chartMarket.resize(); });
})();
