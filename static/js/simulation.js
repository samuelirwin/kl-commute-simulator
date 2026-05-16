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
    fetchApi('carpools', function(data) { state.carpoolData = data; renderCarpools(); });
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

  // Company Table — shows WFH eligibility breakdown in After scenario
  function renderCompanyTable() {
    var tbody = document.getElementById('companyTbody');
    if (!tbody || !state.companies) return;
    var isAfter = state.scenario === 'after';
    tbody.innerHTML = state.companies.map(function(c) {
      var load = isAfter ? c.load_after : c.load_before;
      var pct = Math.round(load * 100);
      var col = load > 0.7 ? '#ff4444' : load > 0.5 ? '#ff8c00' : load > 0.3 ? '#ffd700' : '#39ff7e';
      var startTime = c.assigned_start || '08:00';
      var mode = isAfter
        ? '<span class="mode-badge" style="background:rgba(57,255,126,0.1);color:#39ff7e">' + startTime + '</span>'
        : '<span class="mode-badge" style="background:rgba(255,68,68,0.1);color:#ff4444">' + c.default_start + '</span>';

      // Staff column: show eligible/on-site breakdown in After mode
      var staffCol = '<span style="font-family:\'Space Mono\',monospace;font-size:12px">' + c.staff.toLocaleString() + '</span>';
      if (isAfter && c.wfh_eligible !== undefined) {
        staffCol += '<div style="font-size:9px;margin-top:2px">' +
          '<span style="color:var(--green)">' + c.wfh_count + ' WFH</span>' +
          '<span style="color:var(--muted)"> / </span>' +
          '<span style="color:var(--red)">' + c.on_site_only + ' on-site</span>' +
          '</div>';
      }

      return '<tr>' +
        '<td><div style="font-weight:600;font-size:12px">' + c.name + '</div><div style="font-size:10px;color:var(--muted)">' + c.sector + '</div></td>' +
        '<td>' + staffCol + '</td>' +
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

  // Carpools — aggregate hub-level view for government dashboard
  function renderCarpools() {
    var el = document.getElementById('carpoolList');
    if (!el || !state.carpoolData) return;
    var d = state.carpoolData;
    var isAfter = state.scenario === 'after';
    var colors = ['#00d4ff', '#39ff7e', '#a855f7', '#ffd166', '#ff6b35', '#e63946', '#2196f3', '#ff9800'];

    // Summary stats bar
    var summaryHtml = '<div style="padding:8px 10px;margin-bottom:8px;background:rgba(0,212,255,0.05);border:1px solid var(--border);border-radius:6px">' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">' +
      '<div><div style="font-size:9px;color:var(--muted)">Total Groups</div>' +
      '<div style="font-size:16px;font-weight:700;font-family:\'Space Mono\',monospace;color:' + (isAfter ? 'var(--green)' : 'var(--muted)') + '">' +
      (isAfter ? d.total_groups.toLocaleString() : '0') + '</div></div>' +
      '<div><div style="font-size:9px;color:var(--muted)">Participants</div>' +
      '<div style="font-size:16px;font-weight:700;font-family:\'Space Mono\',monospace;color:' + (isAfter ? 'var(--accent)' : 'var(--muted)') + '">' +
      (isAfter ? d.total_participants.toLocaleString() : '0') + '</div></div>' +
      '<div><div style="font-size:9px;color:var(--muted)">Vehicles Saved</div>' +
      '<div style="font-size:16px;font-weight:700;font-family:\'Space Mono\',monospace;color:' + (isAfter ? 'var(--green)' : 'var(--muted)') + '">' +
      (isAfter ? d.vehicles_saved.toLocaleString() : '0') + '</div></div>' +
      '<div><div style="font-size:9px;color:var(--muted)">Avg Occupancy</div>' +
      '<div style="font-size:16px;font-weight:700;font-family:\'Space Mono\',monospace;color:' + (isAfter ? '#ffd166' : 'var(--muted)') + '">' +
      (isAfter ? d.avg_occupancy + '/seat' : '—') + '</div></div>' +
      '</div></div>';

    // Hub breakdown
    var hubs = d.hubs || [];
    var maxParticipants = 1;
    hubs.forEach(function(h) { if (h.participants > maxParticipants) maxParticipants = h.participants; });

    var hubsHtml = '';
    if (isAfter && hubs.length > 0) {
      hubsHtml = '<div style="font-size:10px;color:var(--muted);margin-bottom:6px;font-weight:600">By Hub Location</div>' +
        hubs.slice(0, 6).map(function(h, i) {
          var pct = Math.round(h.participants / maxParticipants * 100);
          var color = colors[i % colors.length];
          return '<div style="margin-bottom:8px">' +
            '<div style="display:flex;justify-content:space-between;margin-bottom:3px">' +
            '<span style="font-size:11px;color:var(--text)">' + h.hub + '</span>' +
            '<span style="font-size:10px;font-family:\'Space Mono\',monospace;color:' + color + '">' +
            h.groups + ' groups / ' + h.participants + ' people</span>' +
            '</div>' +
            '<div style="height:5px;background:var(--border);border-radius:3px;overflow:hidden">' +
            '<div style="height:100%;width:' + pct + '%;background:' + color + ';border-radius:3px;transition:width 0.8s ease"></div>' +
            '</div>' +
            '<div style="font-size:9px;color:var(--muted);margin-top:2px">' +
            h.zone + ' — ' + h.vehicles_saved + ' vehicles saved</div>' +
            '</div>';
        }).join('');
    } else if (!isAfter) {
      hubsHtml = '<div style="text-align:center;padding:12px;color:var(--muted);font-size:11px">No carpooling active — all single-occupancy trips</div>';
    }

    // Sector breakdown (compact)
    var sectors = d.sectors || [];
    var sectorHtml = '';
    if (isAfter && sectors.length > 0) {
      sectorHtml = '<div style="border-top:1px solid var(--border);margin-top:8px;padding-top:6px">' +
        '<div style="font-size:10px;color:var(--muted);margin-bottom:4px;font-weight:600">By Sector</div>' +
        '<div style="display:flex;flex-wrap:wrap;gap:4px">' +
        sectors.slice(0, 6).map(function(s, i) {
          var color = colors[i % colors.length];
          return '<span style="font-size:10px;padding:2px 8px;border-radius:10px;background:' + color + '15;color:' + color + ';border:1px solid ' + color + '33">' +
            s.sector + ' ' + s.participants + '</span>';
        }).join('') +
        '</div></div>';
    }

    el.innerHTML = summaryHtml + hubsHtml + sectorHtml;
  }

  // WFH Calendar — shows eligibility breakdown per company
  function renderWFH() {
    var el = document.getElementById('wfhCalendar');
    if (!el || !state.wfhData) return;
    var days = ['MON', 'TUE', 'WED', 'THU', 'FRI'];
    var companies = state.wfhData.companies || [];
    var wfhToday = state.wfhData.wfh_today || 0;
    var totalStaff = state.wfhData.total_staff || 0;
    var wfhEligible = state.wfhData.wfh_eligible || 0;
    var bizCritical = state.wfhData.business_critical || 0;
    var isAfter = state.scenario === 'after';

    // Workforce breakdown summary bar
    var summaryHtml = '<div style="margin-bottom:10px;padding:8px 10px;background:rgba(0,212,255,0.05);border:1px solid var(--border);border-radius:6px">' +
      '<div style="display:flex;justify-content:space-between;margin-bottom:6px">' +
      '<span style="font-size:10px;color:var(--muted)">Total Workforce</span>' +
      '<span style="font-size:10px;font-family:\'Space Mono\',monospace;color:var(--text)">' + totalStaff.toLocaleString() + '</span>' +
      '</div>' +
      '<div style="display:flex;justify-content:space-between;margin-bottom:4px">' +
      '<span style="font-size:10px;color:var(--green)">WFH Eligible</span>' +
      '<span style="font-size:10px;font-family:\'Space Mono\',monospace;color:var(--green)">' + wfhEligible.toLocaleString() +
      ' (' + (totalStaff > 0 ? Math.round(wfhEligible / totalStaff * 100) : 0) + '%)</span>' +
      '</div>' +
      '<div style="display:flex;justify-content:space-between;margin-bottom:6px">' +
      '<span style="font-size:10px;color:var(--red)">On-Site Required</span>' +
      '<span style="font-size:10px;font-family:\'Space Mono\',monospace;color:var(--red)">' + bizCritical.toLocaleString() +
      ' (' + (totalStaff > 0 ? Math.round(bizCritical / totalStaff * 100) : 0) + '%)</span>' +
      '</div>' +
      // Stacked bar showing eligible vs on-site
      '<div style="height:6px;background:var(--border);border-radius:3px;overflow:hidden;display:flex">' +
      '<div style="width:' + (totalStaff > 0 ? (wfhEligible / totalStaff * 100) : 0) + '%;background:var(--green);border-radius:3px 0 0 3px"></div>' +
      '<div style="width:' + (totalStaff > 0 ? (bizCritical / totalStaff * 100) : 0) + '%;background:var(--red);border-radius:0 3px 3px 0"></div>' +
      '</div>' +
      (isAfter
        ? '<div style="margin-top:6px;font-size:10px;color:var(--green);font-weight:600">' + wfhToday.toLocaleString() + ' of ' + wfhEligible.toLocaleString() + ' eligible staff WFH today</div>'
        : '<div style="margin-top:6px;font-size:10px;color:var(--muted)">No WFH active — all staff commuting</div>') +
      '</div>';

    // Per-company calendar with eligible/on-site counts
    var calendarHtml = '<div class="wfh-companies">' +
      companies.slice(0, 6).map(function(co) {
        var eligiblePct = co.total_staff > 0 ? Math.round(co.wfh_eligible / co.total_staff * 100) : 0;
        return '<div class="wfh-company-row">' +
          '<div class="wfh-co-name">' + co.name +
          '<div style="font-size:9px;color:var(--muted)">' +
          (isAfter
            ? co.wfh_count + '/' + co.wfh_eligible + ' eligible WFH'
            : co.on_site_only + ' must be on-site') +
          '</div></div>' +
          '<div class="wfh-dots">' +
          co.days.map(function(d, i) {
            var cls = d === 'H' ? 'h' : 'o';
            return '<div class="wfh-dot ' + cls + '" title="' + days[i] + '">' + d + '</div>';
          }).join('') +
          '</div></div>';
      }).join('') +
      '</div>';

    // Legend
    var legendHtml = '<div style="margin-top:8px;display:flex;gap:12px;font-size:10px;color:var(--muted)">' +
      '<span><span style="color:var(--accent)">\u25A0</span> Office</span>' +
      '<span><span style="color:var(--green)">\u25A0</span> WFH</span>' +
      '<span><span style="color:var(--red)">\u25A0</span> On-Site Required</span>' +
      '</div>';

    el.innerHTML = summaryHtml + calendarHtml + legendHtml;
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
    renderCarpools();
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
    var btn = document.getElementById('runSimBtn');
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/dashboard/simulate/');
    xhr.setRequestHeader('X-CSRFToken', getCSRFToken());
    xhr.onload = function() {
      if (xhr.status === 200) {
        try {
          var result = JSON.parse(xhr.responseText);
          if (result.redirect) {
            window.location.href = result.redirect;
          } else if (result.run_id) {
            state.runId = result.run_id;
            loadDashboardData();
            if (btn) { btn.disabled = false; btn.textContent = 'Run Simulation'; }
          }
        } catch (e) {
          console.error('Simulation response error:', e);
          if (btn) { btn.disabled = false; btn.textContent = 'Run Simulation'; }
        }
      } else {
        // Show error feedback
        try {
          var err = JSON.parse(xhr.responseText);
          var msg = err.error || JSON.stringify(err.errors) || 'Simulation failed';
          alert('Simulation error: ' + msg);
        } catch (e) {
          alert('Simulation failed (HTTP ' + xhr.status + ')');
        }
        if (btn) { btn.disabled = false; btn.textContent = 'Run Simulation'; }
      }
    };
    xhr.onerror = function() {
      alert('Network error — could not reach server');
      if (btn) { btn.disabled = false; btn.textContent = 'Run Simulation'; }
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
