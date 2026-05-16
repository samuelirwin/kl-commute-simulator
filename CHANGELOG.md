# Changelog

All notable changes to the MyCommute KL project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-05-16

### Added
- `simulation/engine/routing.py`: corridor graph + Dijkstra path lookup. Each (home_zone, office_zone) pair gets the ordered list of corridor codes on its shortest distance path. Built once per run, used by the traffic simulator to load every trip onto the corridors it actually traverses.
- Origin-Destination breakdown built from the staff list: per-company `{home_zone: staff_count}`. Combined with company start_hour (post-stagger), this becomes per-OD per-slot demand. The traffic simulator routes that demand along the OD's path, capturing through-traffic that the old zone-match heuristic missed entirely (e.g. FEDHWY now carries KLCC-bound trips that pass through PJ→KLSNTRL, not just PJ-bound).
- `compute_od_commute_time_min()`: volume-weighted door-to-desk commute derived from actual path BPR times. For every OD pair, trip_time(slot) = sum of corridor BPR times along the path; weighted by trip count + a 15-min overhead for parking/last-mile.

### Changed
- `peak_vehicles` now measures unique vehicles entering the road system in the peak 15-min slot (computed from OD demand × modal-split car/moto share, minus carpool savings). The old per-corridor max undercounted by picking the busiest single road; a naive corridor-sum would have over-counted because a multi-hop trip touches every corridor on its path. Both alternatives are wrong for a "how many cars are on the road right now?" headline.
- `avg_commute` now derived from path BPR times instead of `corridor_BPR_avg × 3.5 + 15` magic multiplier. The 15-min door-to-desk overhead is preserved as a flat last-mile/parking adjustment; everything else traces back to a network effect.

### Removed
- `_commute_multiplier = 3.5` and the corresponding inflation logic in the runner. Headline commute time is now genuinely derived, not a calibration constant.

### Notes
- BDRUTM zone (Bandar Utama) has no corridors in the seed graph. Astro Malaysia's 850 staff get logged as unreachable and skipped from corridor demand. This is honest about a seed-data gap; adding a Penchala or LDP-North corridor to BDRUTM would fix it in a future iteration.
- The new `peak_congestion=1.0` "before" result is a real characteristic of KL traffic in this model: with proper through-traffic loading, at least one corridor saturates. After-scenario drops to ~0.68. The old model's 0.90 "before" understated saturation because demand wasn't routed correctly.

## [1.5.0] - 2026-05-16

### Changed
- Stagger optimizer rebuilt to be zone-aware and bounded:
  - Per-zone load balancing — two companies sharing a destination zone (e.g. PETRONAS and TM at KLCC) now land in different slots instead of clustering on whichever slot is globally least loaded.
  - Per-company `max_shift_hours` bound (default ±2h) prevents nonsensical shifts (no more AirAsia 07:00 → 10:00 jumps).
  - Per-sector constraint dict honored: Government 07:30–09:00, Banking 07:30–09:30, Manufacturing 06:30–09:00, Construction 06:30–08:30, Aviation 06:00–10:30. Reflects KL operational realities (JPA circular start times, branch hours, multi-shift manufacturing, daylight-sensitive construction).
  - The `capacities` argument is now actually consumed — used as a tiebreaker when two candidate slots produce equal destination-zone load, preferring slots with more spare global capacity.
  - Module docstring no longer claims SLSQP — the implementation is a greedy load-balancer and now says so.
- Carpool willingness now applies to all staff (not just vehicle owners). Drivers are the willing subset whose `primary_transport` is CAR; everyone else willing is a potential rider. Motorcyclists become riders, not drivers, since a motorbike can't carpool meaningfully. Driver seat counts standardized at 4 (sedan: 1 driver + 3 passengers) for willing CAR users.

### Fixed
- Carpool matcher no longer creates single-driver "groups" that remove zero vehicles from the road. A group is only formed when the driver finds at least one passenger.
- Carpool matcher logs filter-rejection reasons (departure-time mismatch vs zone-distance) per destination zone, so sparse matching can be diagnosed.

## [1.4.0] - 2026-05-16

### Added
- Transit boost is now wired into the simulation — when enabled, shifts car commuters to public transit using a 0.4 frequency-vs-ridership elasticity (mid-range of empirical urban-transit studies). Previously the toggle had no effect on results.

### Changed
- `wfh_max_days` slider now caps each company's `wfh_days_per_week` at simulation time, so the policy ceiling actually constrains the WFH planner.
- `wfh_eligibility_pct` slider now controls the WFH fraction in `_apply_wfh_reduction`, `_count_wfh_today`, and `_save_company_results`. Was previously hardcoded at 80% in three places.
- `carpool_willingness_pct` slider now determines which vehicle owners are willing to carpool, seeded by `run.id` for determinism. Was previously ignored — the engine read a static seed-data boolean.
- Modal split `EHL` share now absorbs `100 - (CAR + MCY + PUB)` so the four modes always sum to 100%. Was hardcoded to `4.0%`, allowing totals to exceed 100% which were then silently renormalized.
- Commute time calculation no longer multiplies the "after" value by a `(1 - congestion_benefit)` factor — the BPR volume-delay function already accounts for congestion in `raw_after`. Headline commute numbers are now derived purely from the simulation, not a cosmetic fudge.
- Internal constants renamed for clarity: `_overhead_min` → `_DOOR_TO_DESK_OVERHEAD_MIN`, `_commute_multiplier` → `_CORRIDOR_TO_TRIP_MULTIPLIER`.

### Removed
- `target_peak_vehicles` and `target_avg_commute_min` form fields, model fields, and scaling logic. These were back-fitting headline numbers to user-typed targets, turning the simulator into a calculator that reproduced its own input. If a calibration knob is needed, use `workforce_multiplier` which scales inputs honestly.
- Migration `0004_remove_simulationrun_target_avg_commute_min_and_more.py` drops the columns.

### Fixed
- Carpool vehicle savings were subtracted from every corridor's car volume independently, multiplying the effect by ~22 (one per corridor) and over-stating peak vehicle removal and CO2 reduction. Savings are now distributed across corridors proportionally to each corridor's share of system-wide car volume in the same slot, conserving the total vehicles removed.

## [1.3.0] - 2026-04-20

### Fixed
- Demand profiles now include afternoon return trips (centered ~8.5h after start time with 1.3x wider spread)
- Average commute time now uses volume-weighted calculation — off-peak empty slots no longer dilute the metric
- WFH staff reduction uses company-specific `wfh_days_per_week` rate instead of hardcoded 20%
- Carpool vehicle savings distributed around group departure times using Gaussian, not applied as flat hourly constant
- Corridor demand scaling splits demand among corridors serving the same destination zone to prevent double-counting
- Peak congestion capped at 1.0 in both summary stats and per-record congestion_level
- Stagger optimizer replaced SLSQP (which failed to converge on non-smooth integer demand) with greedy load-balanced slot assignment producing meaningful shifts (e.g., JPM 8:00→7:00, MOF 8:00→9:00)
- Stagger optimizer capacity model uses realistic target throughput instead of raw corridor sum
- Demand profile logging downgraded from INFO to DEBUG to prevent performance degradation during optimization
- Runner WFH count and company result saving now use company-specific WFH fractions

## [1.2.1] - 2026-04-19

### Fixed
- N+1 query in carpool API — replaced `current_members` property call with `Count` annotation to avoid per-group DB hit
- Unbounded full-table scan of StaffMember in company and WFH APIs — replaced Python loop with single `annotate` aggregation query
- Per-company schedule query loop in WFH API — fetches all schedules in one query and groups in Python
- Inline imports in carpool API moved to top-level for better dependency traceability
- Seed command wrapped in `transaction.atomic()` to prevent partial state on failure during re-seed
- Hardcoded `?v=1.1` cache-bust strings replaced with `{% now "U" %}` for automatic invalidation on deploy

## [1.2.0] - 2026-02-28

### Fixed
- Zone lat/lon coordinates now populated with real KL values (were all 0.0, causing zone distance fallback to 15km)
- Commute time estimation now uses lat/lon with flat-earth distance and 25 km/h peak speed (was using canvas coords)
- Pre-computed SimulationRun aggregate values now derived from actual company data (total_staff=38,060) instead of hardcoded inconsistent numbers
- Re-seeding is fully idempotent — `seed_kl_data` deletes old simulation data before regenerating, `seed_sample_staff` clears staff/departments/schedules
- Reference data (zones, corridors) uses `update_or_create` so values are refreshed on re-seed

### Added
- 20 carpool groups pre-seeded across 8 hubs (2-3 groups per hub) for dashboard display
- Real KL latitude/longitude for all 20 zones (e.g. KLCC: 3.1588, 101.7119)

## [1.1.0] - 2026-02-28

### Added
- WFH eligibility breakdown in dashboard — clearly shows total staff vs WFH-eligible vs business-critical (on-site required) roles
- Workforce summary bar in WFH panel with stacked progress bar (green=eligible, red=on-site required)
- Per-company WFH eligibility counts in WFH calendar (e.g. "12/43 eligible WFH" or "7 must be on-site")
- Company table shows WFH/on-site breakdown per company in After scenario
- KPI API returns `total_staff`, `wfh_eligible`, `business_critical` workforce counts
- Company API returns `wfh_eligible` and `on_site_only` counts per company
- WFH API returns global and per-company eligibility breakdown
- Legend updated with "On-Site Required" indicator

### Changed
- Carpool panel redesigned for government-level view — shows aggregate metrics instead of individual group names
- Carpool API now returns hub-level aggregates (groups, participants, vehicles saved per hub) and sector breakdown
- Carpool panel displays summary stats (total groups, participants, vehicles saved, avg occupancy), hub breakdown with progress bars, and sector tags
- Before/After toggle shows "No carpooling active" vs full aggregate data

### Fixed
- Simulation runner `_update_status` only saved the status field, discarding all aggregate results (congestion, commute times, CO2, etc.)
- Now does a full `run.save()` to persist all computed results
- Carpool panel re-renders on Before/After toggle (was missing from `setScenario`)
- Simulation form button re-enables and shows error feedback on failure
- Added cache-busting `?v=1.1` to JS includes to prevent stale browser cache

## [1.0.0] - 2026-02-28

### Added
- Django admin configuration for all models across all 4 apps (core, company, staff, simulation)
- End-to-end verification: all 16 endpoints return HTTP 200
- Git repository initialization with complete project

### Fixed
- Canvas chart gradient color parsing producing invalid `rgbaa(...)` format
- Added 10 sample carpool groups with 27 memberships to seed data

### Verified
- 20 zones, 22 corridors, 8 transit lines, 8 carpool hubs, 4 modal splits
- 25 companies, 75 departments, 1,250 staff members, 6,250 staff schedules
- 1 pre-computed simulation run with 2,816 corridor time slices and 25 company results
- Peak congestion: 0.87 → 0.38 (56% reduction)
- Average commute: 68 → 29 min (57% faster)
- Peak vehicles: 284,000 → 178,000 (37% fewer)
- CO2 saved: 412 tonnes/day

## [0.3.0] - 2026-02-26

### Added
- All 10 HTML templates for the three portal views:
  - `dashboard/index.html`: Government dashboard with map canvas, KPI cards, time chart, impact bars, scenario toggle, ticker bar, company table, stagger chart, carpool groups, WFH calendar, transit load, simulation parameter form with AJAX submit
  - `company/index.html`: Company admin home with company selector, stats cards, department list, simulation result summary, quick links
  - `company/staff_list.html`: Staff list table with transport badges, WFH/carpool indicators, edit links
  - `company/staff_form.html`: Staff add/edit form with backend error display (red text below inputs) and client-side validation via form-validation.js
  - `company/schedule_view.html`: Weekly schedule grid with office/WFH cell styling, start times, departure windows
  - `company/compliance.html`: Compliance dashboard with score bars, color-coded ratings, simulation result columns
  - `staff/index.html`: Personal dashboard with welcome header, weekly schedule cards, carpool summary, quick links
  - `staff/schedule.html`: Personal 5-day schedule with detailed day cards showing start time, departure window, estimated commute
  - `staff/carpool.html`: Carpool group details with member list, role badges, hub info, departure time
  - `staff/impact.html`: Personal impact stats with CO2 savings, WFH impact, commute efficiency bars, company-level results, motivational messaging
- All templates extend base.html, use {% load static %}, and reference proper CSS classes from base.css
- Form templates include both backend validation error display and frontend validation initialization

## [0.2.0] - 2026-02-26

### Added
- Full implementation of 8 simulation engine algorithm modules:
  - `bpr.py`: BPR (Bureau of Public Roads) travel time volume-delay function with input validation
  - `demand.py`: Gaussian demand profile generator with aggregate overlay and integer rounding
  - `stagger.py`: Staggered working hours optimizer using SciPy SLSQP minimization
  - `wfh.py`: WFH rotation planner with sector cap enforcement and greedy day balancing
  - `carpool.py`: Carpool matching engine with zone-based clustering and proximity scoring
  - `co2.py`: CO2 reduction calculator using Malaysian fleet emission factors
  - `traffic_sim.py`: Mesoscopic time-sliced (15-min, 64 slots) BPR-based traffic simulator
  - `runner.py`: Full pipeline orchestrator loading Django models and saving results
- All modules include structured logging, type hints, docstrings, and input validation
- Engine `__init__.py` updated with package-level documentation

## [0.1.0] - 2026-02-26

### Added
- Initial Django project setup with 5 apps: core, simulation, dashboard, company, staff
- Database models for zones, corridors, transit lines, carpool hubs, modal split
- Company and staff member models with department structure
- Simulation models: SimulationRun, CorridorTimeSlice, CompanySimResult
- Carpool group and membership models
- Algorithm engine: BPR travel time, demand profiles, stagger optimizer, WFH planner, carpool matcher, CO2 calculator, traffic simulator, orchestrator
- Seed data command with 20 KL zones, 22 corridors, 25 companies, 8 transit lines, 8 carpool hubs
- Sample staff seed command generating ~1,250 realistic Malaysian staff members
- Pre-computed simulation run with 2,816 corridor time slice records
- Government dashboard with interactive traffic map, KPI cards, charts, and panels
- Company admin portal with staff CRUD, schedule view, and compliance dashboard
- Public staff app with personal schedule, carpool info, and impact stats
- Dark theme UI extracted from prototype HTML
- Request logging middleware
- Comprehensive logging across all modules
