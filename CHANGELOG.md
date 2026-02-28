# Changelog

All notable changes to the MyCommute KL project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
