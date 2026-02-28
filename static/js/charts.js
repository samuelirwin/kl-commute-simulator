/**
 * Chart renderers — draws hourly traffic volume chart and impact breakdown bars.
 * Uses HTML5 Canvas for the time chart and DOM for impact bars.
 */
(function() {
  'use strict';

  var chartData = null;
  var currentScenario = 'before';

  function drawTimeChart() {
    var canvas = document.getElementById('timeChart');
    if (!canvas || !chartData) return;
    var ctx = canvas.getContext('2d');
    var W = canvas.parentElement.offsetWidth - 32;
    var H = 140;
    canvas.width = W;
    canvas.height = H;
    ctx.clearRect(0, 0, W, H);

    var hours = chartData.hours || [];
    var beforeVol = chartData.before_volumes || [];
    var afterVol = chartData.after_volumes || [];
    var n = hours.length;
    if (n === 0) return;

    var padL = 8, padR = 8, padT = 10, padB = 24;
    var chartW = W - padL - padR;
    var chartH = H - padT - padB;

    // Grid lines
    [25, 50, 75, 100].forEach(function(v) {
      var y = padT + chartH * (1 - v / 100);
      ctx.beginPath();
      ctx.moveTo(padL, y); ctx.lineTo(W - padR, y);
      ctx.strokeStyle = 'rgba(30,45,69,0.8)';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.fillStyle = '#3a5070';
      ctx.font = '9px Space Mono';
      ctx.fillText(v + '%', 0, y + 3);
    });

    function drawLine(data, color, fill) {
      ctx.beginPath();
      data.forEach(function(v, i) {
        var x = padL + (i / (n - 1)) * chartW;
        var y = padT + chartH * (1 - v / 100);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      if (fill) {
        ctx.lineTo(padL + chartW, padT + chartH);
        ctx.lineTo(padL, padT + chartH);
        ctx.closePath();
        var grad = ctx.createLinearGradient(0, padT, 0, padT + chartH);
        // Convert any color format to rgba with desired alpha
        var rgbaTop = color.indexOf('rgba') === 0
          ? color.replace(/,[^,)]+\)$/, ',0.3)')
          : color.replace('rgb(', 'rgba(').replace(')', ',0.3)');
        var rgbaBot = color.indexOf('rgba') === 0
          ? color.replace(/,[^,)]+\)$/, ',0)')
          : color.replace('rgb(', 'rgba(').replace(')', ',0)');
        grad.addColorStop(0, rgbaTop);
        grad.addColorStop(1, rgbaBot);
        ctx.fillStyle = grad;
        ctx.fill();
        ctx.beginPath();
        data.forEach(function(v, i) {
          var x = padL + (i / (n - 1)) * chartW;
          var y = padT + chartH * (1 - v / 100);
          i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        });
      }
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    drawLine(beforeVol, 'rgba(255,68,68,1)', true);
    drawLine(afterVol, 'rgba(57,255,126,1)', true);

    // Hour labels
    hours.forEach(function(h, i) {
      if (i % 2 !== 0) return;
      var x = padL + (i / (n - 1)) * chartW;
      ctx.fillStyle = '#3a5070';
      ctx.font = '9px Space Mono';
      ctx.textAlign = 'center';
      ctx.fillText(h, x, H - 6);
    });

    // Legend
    ctx.fillStyle = '#ff4444'; ctx.fillRect(padL, padT, 20, 3);
    ctx.fillStyle = '#5a7a9e'; ctx.font = '10px Sora';
    ctx.textAlign = 'left'; ctx.fillText('Before', padL + 24, padT + 5);
    ctx.fillStyle = '#39ff7e'; ctx.fillRect(padL + 80, padT, 20, 3);
    ctx.fillStyle = '#5a7a9e'; ctx.fillText('After', padL + 104, padT + 5);
  }

  function renderImpactBars(impactData) {
    var el = document.getElementById('impact-bars');
    if (!el) return;

    var measures = impactData || [
      { label: 'Staggered Hours', value: 28, color: '#00d4ff', unit: '% congestion reduced' },
      { label: 'WFH Rotation', value: 22, color: '#39ff7e', unit: '% vehicles removed' },
      { label: 'Carpooling', value: 18, color: '#a855f7', unit: '% trip reduction' },
      { label: 'Public Transit', value: 12, color: '#ffd166', unit: '% modal shift' }
    ];

    var isAfter = currentScenario === 'after';
    el.innerHTML = measures.map(function(m) {
      var val = isAfter ? m.value : 0;
      return '<div style="margin-bottom:10px">' +
        '<div style="display:flex;justify-content:space-between;margin-bottom:4px">' +
        '<span style="font-size:11px;color:var(--muted)">' + m.label + '</span>' +
        '<span style="font-size:11px;font-family:\'Space Mono\',monospace;color:' + m.color + '">' +
        (isAfter ? '+' + val : '0') + '%</span>' +
        '</div>' +
        '<div style="height:6px;background:var(--border);border-radius:3px;overflow:hidden">' +
        '<div style="height:100%;width:' + val + '%;background:' + m.color + ';border-radius:3px;transition:width 1.5s ease;max-width:100%"></div>' +
        '</div></div>';
    }).join('');
  }

  // Public API
  window.Charts = {
    init: function(data) {
      chartData = data;
      drawTimeChart();
      renderImpactBars();
    },
    setScenario: function(s) {
      currentScenario = s;
      drawTimeChart();
      renderImpactBars();
    },
    renderImpact: renderImpactBars,
    redraw: drawTimeChart
  };

  window.addEventListener('resize', function() { drawTimeChart(); });
})();
