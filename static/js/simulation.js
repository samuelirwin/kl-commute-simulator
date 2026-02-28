/**
 * Main simulation controller — handles scenario toggling, API fetching,
 * simulation clock, and panel rendering for the dashboard.
 */
(function() {
  'use strict';

  var state = {
    scenario: 'before',
    simRunning: true,
    simMinutes: 7 * 60,
    runId: null,
    kpis: null,
    companies: null,
    staggerData: null,
    carpoolData: null,
    wfhData: null,
    transitData: null
  };

  // Fetch JSON from API with error handling
  function fetchApi(endpoint, callback) {
    if (!state.runId) return;
    var url = '/api/v1/simulation/' + state.runId + '/' + endpoint + '/';
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.onload = function() {
      if (xhr.status === 200) {
        try {
          callback(JSON.parse(xhr.responseText));
        } catch (e) {
          console.error('JSON parse error for ' + endpoint + ':', e);
        }
      }
    };
    xhr.onerror = function() { console.error('Fetch error for ' + endpoint); };
    xhr.send();
  }

  // Load all dashboard data from API
  function loadDashboardData() {
    fetchApi('kpis', function(data) { state.kpis = data; updateKPIs(); });
    fetchApi('map', function(data) { if (window.TrafficMap) window.TrafficMap.init(data); });
    fetchApi('chart', function(data) { if (window.Charts) window.Charts.init(data); });
    fetchApi('companies', function(data) { state.companies = data.companies; renderCompanyTable(); });
    fetchApi('stagger', function(data) { state.staggerData = data.slots; renderStagger(); });
    fetchApi('carpools', function(data) { state.carpoolData = data.groups; renderCarpools(); });
    fetchApi('wfh', function(data) { state.wfhData = data; renderWFH(); });
    fetchApi('transit', function(data) { state.transitData = data.lines; renderTransit(); });
  }

  // KPI Cards
  function updateKPIs() {
    if (!state.kpis) return;
    var k = state.kpis;
    var isBefore = state.scenario === 'before';

    // Congestion
    setKPI('congestion',
      isBefore ? Math.round(k.peak_congestion_before * 100) + '%' : Math.round(k.peak_congestion_after * 100) + '%',
      isBefore ? 'Status Quo' : '\u25BC ' + k.congestion_reduction_pct + '% reduction',
      isBefore ? 'bad' : 'good',
      isBefore ? '#ff4444' : '#39ff7e'
    );

    // Commute time
    setKPI('time',
      isBefore ? Math.round(k.avg_commute_before) + '<span style="font-size:16px">min</span>' : Math.round(k.avg_commute_after) + '<span style="font-size:16px">min</span>',
      isBefore ? 'Baseline' : '\u25BC ' + k.commute_reduction_pct + '% faster',
      isBefore ? 'bad' : 'good',
      isBefore ? '#ffd166' : '#ffd166'
    );

    // Vehicles
    var vBefore = k.peak_vehicles_before >= 1000 ? Math.round(k.peak_vehicles_before / 1000) + 'K' : k.peak_vehicles_before;
    var vAfter = k.peak_vehicles_after >= 1000 ? Math.round(k.peak_vehicles_after / 1000) + 'K' : k.peak_vehicles_after;
    var removed = k.vehicles_removed >= 1000 ? Math.round(k.vehicles_removed / 1000) + 'K' : k.vehicles_removed;
    setKPI('vehicles',
      isBefore ? vBefore : vAfter,
      isBefore ? 'Baseline' : '\u25BC ' + removed + ' fewer',
      isBefore ? 'bad' : 'good',
      '#39ff7e'
    );

    // CO2
    setKPI('co2',
      isBefore ? '0<span style="font-size:16px">t</span>' : Math.round(k.co2_saved_tonnes) + '<span style="font-size:16px">t</span>',
      isBefore ? 'No saving' : '\u25B2 ' + Math.round(k.co2_saved_tonnes) + ' tonnes saved',
      isBefore ? 'bad' : 'good',
      '#00d4ff'
    );
  }

  function setKPI(id, value, delta, deltaClass, cardColor) {
    var valEl = document.getElementById('val-' + id);
    var deltaEl = document.getElementById('delta-' + id);
    var cardEl = document.getElementById('kpi-' + id);
    if (valEl) valEl.innerHTML = value;
    if (deltaEl) { deltaEl.className = 'kpi-delta ' + deltaClass; deltaEl.textContent = delta; }
    if (cardEl && cardColor) cardEl.style.setProperty('--card-color', cardColor);
  }

  // Company Table
  function renderCompanyTable() {
    var tbody = document.getElementById('companyTbody');
    if (!tbody || !state.companies) return;
    tbody.innerHTML = state.companies.map(function(c) {
      var load = state.scenario === 'before' ? c.load_before : c.load_after;
      var pct = Math.round(load * 100);
      var col = load > 0.7 ? '#ff4444' : load > 0.5 ? '#ff8c00' : load > 0.3 ? '#ffd700' : '#39ff7e';
      var startTime = c.assigned_start || '08:00';
      var mode = state.scenario === 'after'
        ? '<span class="mode-badge" style="background:rgba(57,255,126,0.1);color:#39ff7e">' + startTime + '</span>'
        : '<span class="mode-badge" style="background:rgba(255,68,68,0.1);color:#ff4444">' + c.default_start + '</span>';
      return '<tr>' +
        '<td><div style="font-weight:600;font-size:12px">' + c.name + '</div><div style="font-size:10px;color:var(--muted)">' + c.sector + '</div></td>' +
        '<td style="font-family:\'Space Mono\',monospace;font-size:12px">' + c.staff.toLocaleString() + '</td>' +
        '<td>' + mode + '</td>' +
        '<td><div class="traffic-bar"><div class="traffic-fill" style="width:' + pct + '%;background:' + col + '"></div></div>' +
        '<div style="font-size:10px;color:' + col + ';margin-top:2px">' + pct + '%</div></td>' +
        '</tr>';
    }).join('');
  }

  // Stagger Chart
  function renderStagger() {
    var el = document.getElementById('staggerPanel');
    if (!el || !state.staggerData) return;
    var maxCount = 0;
    state.staggerData.forEach(function(s) {
      var v = Math.max(s.count_before, s.count_after);
      if (v > maxCount) maxCount = v;
    });
    if (maxCount === 0) maxCount = 1;

    var colors = ['#00d4ff', '#ff6b35', '#ffd166', '#a855f7', '#39ff7e', '#e63946', '#ff9800', '#2196f3'];
    el.innerHTML = state.staggerData.map(function(s, i) {
      var count = state.scenario === 'before' ? s.count_before : s.count_after;
      var pct = (count / maxCount) * 100;
      var color = colors[i % colors.length];
      return '<div class="stagger-slot">' +
        '<div class="stagger-time">' + s.time + '</div>' +
        '<div class="stagger-bar-wrap">' +
        '<div class="stagger-bar" style="width:' + pct + '%;background:' + color + ';min-width:' + (count > 0 ? '20px' : '0') + '">' +
        (count > 5 ? s.label : '') + '</div>' +
        '</div>' +
        '<div class="stagger-count">' + count + 'K</div>' +
        '</div>';
    }).join('');
  }

  // Carpools
  function renderCarpools() {
    var el = document.getElementById('carpoolList');
    if (!el || !state.carpoolData) return;
    var colors = ['#00d4ff', '#ff6b35', '#39ff7e', '#ffd166', '#a855f7'];
    var icons = ['\uD83D\uDE97', '\uD83D\uDE99', '\uD83D\uDE97', '\uD83D\uDE99', '\uD83D\uDE97'];
    el.innerHTML = state.carpoolData.slice(0, 6).map(function(c, i) {
      return '<div class="carpool-item">' +
        '<div class="carpool-avatar" style="background:' + colors[i % 5] + '22;color:' + colors[i % 5] + '">' + icons[i % 5] + '</div>' +
        '<div class="carpool-info">' +
        '<div class="carpool-name">' + c.name + '</div>' +
        '<div class="carpool-route">' + c.route + '</div>' +
        '</div>' +
        '<div class="carpool-seats">' + c.members + '/' + c.max_seats + '</div>' +
        '</div>';
    }).join('');
  }

  // WFH Calendar
  function renderWFH() {
    var el = document.getElementById('wfhCalendar');
    if (!el || !state.wfhData) return;
    var days = ['MON', 'TUE', 'WED', 'THU', 'FRI'];
    var companies = state.wfhData.companies || [];
    var wfhToday = state.wfhData.wfh_today || 0;

    el.innerHTML = '<div class="wfh-companies">' +
      companies.slice(0, 6).map(function(co) {
        return '<div class="wfh-company-row">' +
          '<div class="wfh-co-name">' + co.name + '</div>' +
          '<div class="wfh-dots">' +
          co.days.map(function(d, i) {
            var cls = d === 'H' ? 'h' : 'o';
            return '<div class="wfh-dot ' + cls + '" title="' + days[i] + '">' + d + '</div>';
          }).join('') +
          '</div></div>';
      }).join('') +
      '</div>' +
      '<div style="margin-top:8px;display:flex;gap:12px;font-size:10px;color:var(--muted)">' +
      '<span><span style="color:var(--accent)">\u25A0</span> Office</span>' +
      '<span><span style="color:var(--green)">\u25A0</span> WFH</span>' +
      (state.scenario === 'after'
        ? '<span style="color:var(--green);font-weight:700">' + wfhToday.toLocaleString() + ' off roads today \u2713</span>'
        : '<span style="color:var(--red)">All in-office</span>') +
      '</div>';
  }

  // Transit
  function renderTransit() {
    var el = document.getElementById('transitList');
    if (!el || !state.transitData) return;
    el.innerHTML = state.transitData.map(function(t) {
      var load = state.scenario === 'after' ? t.load_after : t.load_before;
      var pct = state.scenario === 'after' ? t.pct_after : t.pct_before;
      return '<div class="transit-item">' +
        '<div class="transit-line" style="background:' + t.color + '22;color:' + t.color + '">' + t.code + '</div>' +
        '<div class="transit-info">' +
        '<div class="transit-name">' + t.name + '</div>' +
        '<div class="transit-detail">' + t.route + '</div>' +
        '</div>' +
        '<div class="transit-load ' + load + '">' + pct + '</div>' +
        '</div>';
    }).join('');
  }

  // Scenario toggle
  function setScenario(s) {
    state.scenario = s;
    document.getElementById('tab-before').className = 'scenario-tab before' + (s === 'before' ? ' active' : '');
    document.getElementById('tab-after').className = 'scenario-tab after' + (s === 'after' ? ' active' : '');
    updateKPIs();
    renderCompanyTable();
    renderStagger();
    renderWFH();
    renderTransit();
    if (window.TrafficMap) window.TrafficMap.setScenario(s);
    if (window.Charts) window.Charts.setScenario(s);
  }

  // Simulation clock
  function startSimClock() {
    setInterval(function() {
      if (!state.simRunning) return;
      state.simMinutes += 2;
      if (state.simMinutes >= 22 * 60) state.simMinutes = 6 * 60;
      var h = Math.floor(state.simMinutes / 60);
      var m = state.simMinutes % 60;
      var ampm = h >= 12 ? 'PM' : 'AM';
      var h12 = h > 12 ? h - 12 : h === 0 ? 12 : h;
      var el = document.getElementById('simTime');
      if (el) el.innerText = String(h12).padStart(2, '0') + ':' + String(m).padStart(2, '0') + ' ' + ampm;
    }, 200);
  }

  function togglePlay() {
    state.simRunning = !state.simRunning;
    var btn = document.getElementById('playBtn');
    if (btn) btn.innerText = state.simRunning ? '\u23F8 Pause' : '\u25B6 Play';
    if (state.simRunning && window.TrafficMap) window.TrafficMap.start();
    else if (window.TrafficMap) window.TrafficMap.stop();
  }

  function resetSim() {
    state.simMinutes = 7 * 60;
    setScenario('before');
  }

  // Run new simulation
  function runSimulation(formData) {
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/dashboard/simulate/');
    xhr.setRequestHeader('X-CSRFToken', getCSRFToken());
    xhr.onload = function() {
      if (xhr.status === 200) {
        try {
          var result = JSON.parse(xhr.responseText);
          if (result.run_id) {
            state.runId = result.run_id;
            loadDashboardData();
          }
          if (result.redirect) {
            window.location.href = result.redirect;
          }
        } catch (e) {
          console.error('Simulation response error:', e);
        }
      }
    };
    xhr.send(formData);
  }

  function getCSRFToken() {
    var cookie = document.cookie.split(';').find(function(c) { return c.trim().startsWith('csrftoken='); });
    return cookie ? cookie.split('=')[1] : '';
  }

  // Public API
  window.Simulation = {
    init: function(runId) {
      state.runId = runId;
      loadDashboardData();
      startSimClock();
    },
    setScenario: setScenario,
    togglePlay: togglePlay,
    resetSim: resetSim,
    runSimulation: runSimulation,
    getState: function() { return state; }
  };
})();
