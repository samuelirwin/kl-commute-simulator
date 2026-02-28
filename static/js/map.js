/**
 * Traffic map renderer — draws zones, corridors, carpool hubs, and animated vehicles
 * on an HTML5 canvas. Data is fetched from the simulation API.
 */
(function() {
  'use strict';

  let mapData = null;
  let vehicles = [];
  let animFrame = null;
  let scenario = 'before';

  function getTrafficColor(cong, alpha) {
    if (cong > 0.75) return 'rgba(255,68,68,' + alpha + ')';
    if (cong > 0.55) return 'rgba(255,140,0,' + alpha + ')';
    if (cong > 0.35) return 'rgba(255,215,0,' + alpha + ')';
    return 'rgba(57,255,126,' + alpha + ')';
  }

  function initVehicles(W, H) {
    vehicles = [];
    if (!mapData || !mapData.roads) return;
    mapData.roads.forEach(function(road, ri) {
      var count = scenario === 'before' ? 6 : 2;
      for (var i = 0; i < count; i++) {
        vehicles.push({
          roadIdx: ri,
          t: Math.random(),
          speed: 0.002 + Math.random() * 0.003,
          dir: Math.random() > 0.5 ? 1 : -1
        });
      }
    });
  }

  function drawVehicles(ctx, W, H) {
    vehicles.forEach(function(v) {
      v.t += v.speed * v.dir;
      if (v.t > 1) v.t = 0;
      if (v.t < 0) v.t = 1;

      var road = mapData.roads[v.roadIdx];
      if (!road) return;
      var cong = scenario === 'before' ? road.congestion_before : road.congestion_after;
      var x = (road.from_x + (road.to_x - road.from_x) * v.t) * W;
      var y = (road.from_y + (road.to_y - road.from_y) * v.t) * H;

      ctx.beginPath();
      ctx.arc(x, y, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = getTrafficColor(cong, 1);
      ctx.fill();
    });
  }

  function drawMap() {
    var canvas = document.getElementById('mapCanvas');
    if (!canvas || !mapData) return;
    var ctx = canvas.getContext('2d');
    var W = canvas.offsetWidth;
    var H = canvas.offsetHeight;
    canvas.width = W;
    canvas.height = H;

    ctx.clearRect(0, 0, W, H);

    // Background gradient
    var bg = ctx.createRadialGradient(W * 0.5, H * 0.5, 0, W * 0.5, H * 0.5, W * 0.6);
    bg.addColorStop(0, '#0d1420');
    bg.addColorStop(1, '#060a12');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);

    // Draw roads
    mapData.roads.forEach(function(road) {
      var cong = scenario === 'before' ? road.congestion_before : road.congestion_after;
      var x1 = road.from_x * W, y1 = road.from_y * H;
      var x2 = road.to_x * W, y2 = road.to_y * H;

      // Road glow
      ctx.beginPath();
      ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
      ctx.strokeStyle = getTrafficColor(cong, 0.15);
      ctx.lineWidth = 12;
      ctx.stroke();

      // Road line
      ctx.beginPath();
      ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
      ctx.strokeStyle = getTrafficColor(cong, 0.9);
      ctx.lineWidth = 3;
      ctx.stroke();

      // Road label
      var mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
      ctx.fillStyle = 'rgba(90,122,158,0.7)';
      ctx.font = '9px Sora';
      ctx.textAlign = 'center';
      ctx.fillText(road.name, mx, my - 4);
    });

    // Carpool hubs
    if (mapData.carpool_hubs) {
      mapData.carpool_hubs.forEach(function(hub) {
        var x = hub.x * W, y = hub.y * H;
        ctx.beginPath();
        ctx.arc(x, y, 8, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(168,85,247,0.3)';
        ctx.fill();
        ctx.strokeStyle = '#a855f7';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        if (scenario === 'after') {
          ctx.beginPath();
          var r = 12 + (Date.now() % 1500) / 1500 * 10;
          ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.strokeStyle = 'rgba(168,85,247,' + (0.5 - (Date.now() % 1500) / 3000) + ')';
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      });
    }

    // Vehicles
    drawVehicles(ctx, W, H);

    // Landmarks
    mapData.landmarks.forEach(function(lm) {
      var x = lm.x * W, y = lm.y * H;
      var r = lm.major ? 10 : 7;

      ctx.beginPath();
      ctx.arc(x, y, r + 4, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(0,212,255,0.08)';
      ctx.fill();

      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = '#0d1420';
      ctx.fill();
      ctx.strokeStyle = lm.major ? 'rgba(0,212,255,0.8)' : 'rgba(0,212,255,0.4)';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      ctx.font = lm.major ? '11px Sora' : '9px Sora';
      ctx.textAlign = 'center';
      ctx.fillStyle = lm.major ? '#e8f0fe' : '#5a7a9e';
      ctx.fillText(lm.name, x, y + r + 12);
    });

    // Update congestion label
    var avgCong = scenario === 'before' ? (mapData.avg_congestion_before || 0.87) : (mapData.avg_congestion_after || 0.38);
    var label = avgCong > 0.7 ? 'CRITICAL' : avgCong > 0.5 ? 'HEAVY' : avgCong > 0.3 ? 'MODERATE' : 'FREE-FLOWING';
    var col = avgCong > 0.7 ? 'var(--red)' : avgCong > 0.5 ? 'var(--orange)' : avgCong > 0.3 ? 'var(--yellow)' : 'var(--green)';
    var clEl = document.getElementById('congestionLevel');
    if (clEl) clEl.innerHTML = 'CONGESTION: <span style="color:' + col + '">' + label + '</span>';
  }

  function animate() {
    drawMap();
    animFrame = requestAnimationFrame(animate);
  }

  function startAnimation() {
    if (animFrame) cancelAnimationFrame(animFrame);
    animate();
  }

  function stopAnimation() {
    if (animFrame) {
      cancelAnimationFrame(animFrame);
      animFrame = null;
    }
  }

  // Public API
  window.TrafficMap = {
    init: function(data) {
      mapData = data;
      var canvas = document.getElementById('mapCanvas');
      if (canvas) {
        initVehicles(canvas.offsetWidth, canvas.offsetHeight);
        startAnimation();
      }
    },
    setScenario: function(s) {
      scenario = s;
      var canvas = document.getElementById('mapCanvas');
      if (canvas) {
        initVehicles(canvas.offsetWidth, canvas.offsetHeight);
      }
    },
    refresh: function() { drawMap(); },
    stop: stopAnimation,
    start: startAnimation
  };

  window.addEventListener('resize', function() { drawMap(); });
})();
