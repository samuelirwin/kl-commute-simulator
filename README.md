# MyCommute KL — Smart Commute Coordination System

A government-level traffic simulation platform for the Klang Valley (Greater Kuala Lumpur) that models the impact of staggered working hours, WFH rotation, carpooling, and transit frequency boosts on peak-hour congestion.

Built with Django 5.2, SciPy, and NumPy.

## Features

- **Traffic Simulation Engine** — BPR-based mesoscopic simulator with 22 corridors, 64 time slots (15-min intervals), and before/after scenario comparison
- **OD Routing** — corridor graph + Dijkstra shortest-path lookup so each (home_zone, office_zone) trip loads its actual path corridors instead of being attributed to whichever corridor happens to terminate at the destination zone
- **Stagger Optimizer** — zone-aware greedy load balancer with per-company max-shift bound (±2h default) and per-sector start-time constraints (Government 07:30–09:00, Banking 07:30–09:30, Manufacturing 06:30–09:00, Construction 06:30–08:30, Aviation 06:00–10:30)
- **WFH Rotation Planner** — sector-capped WFH scheduling with greedy day balancing; respects the run's `wfh_max_days` ceiling and `wfh_eligibility_pct` rate
- **Carpool Matcher** — zone-based clustering with proximity scoring and detour tolerance; only forms groups when a driver finds at least one passenger; willingness-weighted across the full staff list
- **Transit Boost** — frequency increase shifts car-mode commuters to public transit using a 0.4 ridership-vs-frequency elasticity
- **CO2 Calculator** — Malaysian fleet emission factors (MARii) for reduction estimation
- **Government Dashboard** — interactive dark-theme dashboard with live traffic map, KPI cards, hourly charts, company load table, stagger distribution, carpool impact, WFH calendar, and transit load panels
- **Company Admin Portal** — staff management, schedule views, and compliance dashboard
- **Staff Portal** — personal schedule, carpool group info, and impact stats

## Prerequisites

- Python 3.11+
- pip

## Getting Started

### 1. Clone and set up the virtual environment

```bash
git clone <repository-url>
cd kl-commute-simulator
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run database migrations

```bash
python manage.py migrate
```

### 4. Seed reference data

This creates 20 zones, 22 corridors, 8 transit lines, 8 carpool hubs, 4 modal splits, 25 companies, and one pre-computed simulation run.

```bash
python manage.py seed_kl_data
```

### 5. Seed sample staff members

Generates staff members across companies with home zones, WFH eligibility, carpool preferences, and weekly schedules.

```bash
python manage.py seed_sample_staff
```

### 6. Start the development server

```bash
python manage.py runserver
```

### 7. Open the dashboard

Navigate to **http://127.0.0.1:8000/** in your browser. The pre-seeded simulation results will load immediately.

## Running a New Simulation

1. Click the **Parameters** button (top-right) on the dashboard
2. Configure the simulation settings:
   - **Run Name** — label for this simulation run
   - **Stagger Window** — start/end times for the stagger range (default 07:00–10:30)
   - **Max WFH Days/Week** — maximum WFH days per week (default 2)
   - **WFH Sector Cap (%)** — max percentage of staff WFH per sector (default 40%)
   - **Carpool Max Detour (km)** — km detour tolerance for carpool matching (default 5.0)
   - **Transit Boost (%)** — transit frequency increase percentage (default 20%)
   - Toggle on/off: Staggered Hours, WFH Rotation, Carpooling, Transit Boost
3. Click **Run Simulation**
4. The page redirects to the new run's dashboard with before/after results

## Viewing Results

Use the two scenario tabs at the top of the dashboard to compare:

- **Before** — status quo (each company uses its seeded default start time, no coordination)
- **After** — with all enabled optimizations applied

All panels update when toggling: KPI cards, traffic map, company load table, stagger chart, carpool impact, WFH calendar, and transit load.

Past simulation runs are listed at the bottom of the dashboard and can be viewed individually.

## What this model is honest about

- **Peak congestion drops meaningfully** when stagger + WFH + carpool + transit boost are stacked (~30% reduction at default settings). Peak-hour V/C ratio on the worst corridors falls from saturation toward free-flow.
- **Average door-to-desk commute barely moves**. Peak-spreading flattens the demand curve without shortening any individual trip — that is what a load-balancing intervention does in reality. Headline numbers claiming "57% faster commute" from peak-spreading alone would be a fiction.
- **`peak_vehicles`** counts unique vehicles entering the road in the worst 15-min slot (derived from OD demand × modal split, minus carpool savings). Not a per-corridor max (under-counted) and not a sum across corridors (double-counted multi-hop trips).
- **`avg_commute`** is derived from path BPR sums + a flat 15-min last-mile/parking overhead. No `× N` calibration multiplier inflates the headline.
- **Carpool savings** are distributed proportionally across corridors based on each corridor's share of system-wide cars in the same slot — conserving the total vehicles removed.

## Known limitations

- **BDRUTM (Bandar Utama)** has no corridors in the seed graph. Astro Malaysia's 850 staff are logged as unreachable and skipped from corridor demand. Adding a connecting corridor in `core/management/commands/seed_kl_data.py` would close this gap.
- **Departure-time variance** is the same for every staff member (σ=0.5h), independent of trip distance.
- **Path routing** is undirected and weighted by distance only. A faster but longer toll road competes equally with a shorter free road. Time-cost weighting would be a one-line change.
- **Stagger does not update individual staff departure_hour** after company start times shift, so the carpool matcher still pairs riders by their *seeded* departure times rather than post-stagger ones.

## Project Structure

```
kl-commute-simulator/
├── core/                  # Reference data models (zones, corridors, transit, hubs)
│   └── management/commands/
│       ├── seed_kl_data.py        # Seed all reference data and pre-computed run
│       └── seed_sample_staff.py   # Generate sample staff members
├── company/               # Company and staff member models, admin portal views
├── staff/                 # Carpool group/membership models, staff portal views
├── simulation/            # Simulation run models and API views
│   └── engine/            # Algorithm modules
│       ├── bpr.py         # BPR volume-delay function
│       ├── demand.py      # Gaussian demand profile generator
│       ├── routing.py     # Corridor graph + Dijkstra OD path lookup
│       ├── stagger.py     # Zone-aware greedy stagger optimizer
│       ├── wfh.py         # WFH rotation planner
│       ├── carpool.py     # Carpool matching engine
│       ├── co2.py         # CO2 reduction calculator
│       ├── traffic_sim.py # Mesoscopic traffic simulator
│       └── runner.py      # Full pipeline orchestrator
├── dashboard/             # Government dashboard views and forms
├── templates/             # HTML templates (base, dashboard, company, staff)
├── static/                # CSS and JavaScript (map, charts, simulation controller)
├── mycommute/             # Django project settings and root URL config
├── requirements.txt
└── CHANGELOG.md
```

## API Endpoints

All simulation data is served as JSON from `/api/v1/simulation/<run_id>/`:

| Endpoint     | Description                                          |
|--------------|------------------------------------------------------|
| `kpis/`      | KPI card data (congestion, commute, vehicles, CO2)   |
| `map/`       | Map landmarks, roads with congestion, carpool hubs   |
| `corridors/` | Time-sliced corridor data for charts                 |
| `companies/` | Company coordination table with load metrics         |
| `chart/`     | Hourly traffic volume (before vs after)              |
| `stagger/`   | Stagger time slot distribution                       |
| `carpools/`  | Aggregate carpool metrics by hub and sector          |
| `wfh/`       | WFH calendar with eligibility breakdown              |
| `transit/`   | Transit line load data                               |

## Tech Stack

- **Backend**: Django 5.2, SQLite
- **Algorithms**: NumPy (vectorized demand + corridor matrices), SciPy (available for future optimization work), pure-Python heapq Dijkstra for OD routing
- **Frontend**: Vanilla JavaScript, HTML5 Canvas (traffic map), Chart.js-style rendering
- **Styling**: Custom dark theme CSS

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history. Notable milestones:

- **2.0.0** — OD routing, derived headline metrics, no more back-fit multipliers
- **1.5.0** — Zone-aware stagger optimizer, real carpool driver/rider matching
- **1.4.0** — Transit boost wiring, modal-split EHL clamp fix, slider plumbing
- **1.3.1** — Carpool per-corridor savings distribution fix
- **1.0.0** — Initial release