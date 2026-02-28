"""
Management command to seed all reference data for the MyCommute KL system.

Seeds zones, corridors, transit lines, carpool hubs, modal splits, companies,
and one pre-computed SimulationRun with CorridorTimeSlice + CompanySimResult records.
Uses get_or_create for idempotency so the command can be safely re-run.
"""
import logging
import math
from datetime import time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from company.models import Company
from core.models import CarpoolHub, Corridor, ModalSplit, TransitLine, Zone
from simulation.models import CompanySimResult, CorridorTimeSlice, SimulationRun

logger = logging.getLogger("core")


# ---------------------------------------------------------------------------
# Static seed data definitions
# ---------------------------------------------------------------------------

ZONES = [
    {"name": "KLCC / Petronas Towers", "code": "KLCC", "map_x": 0.55, "map_y": 0.38, "is_major": True, "icon": "office", "population": 45000},
    {"name": "KL Sentral", "code": "KLSNTRL", "map_x": 0.42, "map_y": 0.55, "is_major": True, "icon": "train", "population": 35000},
    {"name": "Bukit Bintang", "code": "BKTBNTG", "map_x": 0.52, "map_y": 0.48, "is_major": False, "icon": "shop", "population": 28000},
    {"name": "Chow Kit", "code": "CHWKIT", "map_x": 0.50, "map_y": 0.28, "is_major": False, "icon": "market", "population": 22000},
    {"name": "Damansara Heights", "code": "DMSRA", "map_x": 0.20, "map_y": 0.30, "is_major": True, "icon": "office", "population": 85000},
    {"name": "Subang Jaya", "code": "SUBANG", "map_x": 0.10, "map_y": 0.60, "is_major": True, "icon": "house", "population": 380000},
    {"name": "Shah Alam", "code": "SHAHALAM", "map_x": 0.08, "map_y": 0.72, "is_major": True, "icon": "gov", "population": 650000},
    {"name": "Petaling Jaya", "code": "PJ", "map_x": 0.22, "map_y": 0.65, "is_major": True, "icon": "city", "population": 620000},
    {"name": "Cheras", "code": "CHERAS", "map_x": 0.60, "map_y": 0.72, "is_major": True, "icon": "house", "population": 450000},
    {"name": "Ampang", "code": "AMPANG", "map_x": 0.72, "map_y": 0.40, "is_major": False, "icon": "house", "population": 180000},
    {"name": "Mont Kiara", "code": "MNTKRA", "map_x": 0.35, "map_y": 0.22, "is_major": False, "icon": "condo", "population": 65000},
    {"name": "Puchong", "code": "PUCHONG", "map_x": 0.18, "map_y": 0.82, "is_major": True, "icon": "house", "population": 350000},
    {"name": "Kepong", "code": "KEPONG", "map_x": 0.38, "map_y": 0.15, "is_major": False, "icon": "industry", "population": 280000},
    {"name": "Klang", "code": "KLANG", "map_x": 0.03, "map_y": 0.70, "is_major": True, "icon": "city", "population": 520000},
    {"name": "Cyberjaya", "code": "CYBER", "map_x": 0.22, "map_y": 0.90, "is_major": False, "icon": "tech", "population": 45000},
    {"name": "Putrajaya", "code": "PTRJAYA", "map_x": 0.40, "map_y": 0.92, "is_major": True, "icon": "gov", "population": 110000},
    {"name": "Bangsar", "code": "BNGSR", "map_x": 0.38, "map_y": 0.58, "is_major": False, "icon": "cafe", "population": 48000},
    {"name": "Setapak", "code": "STPK", "map_x": 0.55, "map_y": 0.22, "is_major": False, "icon": "house", "population": 180000},
    {"name": "Kajang", "code": "KAJANG", "map_x": 0.65, "map_y": 0.88, "is_major": False, "icon": "house", "population": 340000},
    {"name": "Bandar Utama", "code": "BDRUTM", "map_x": 0.15, "map_y": 0.42, "is_major": False, "icon": "mall", "population": 120000},
]

CORRIDORS = [
    {"name": "Jalan Ampang", "code": "JLNAMPANG", "from": "KLCC", "to": "AMPANG", "distance_km": 8, "free_flow_speed_kmh": 50, "capacity_vph": 4500, "daily_volume": 85000, "is_tolled": False, "toll_rate": "0.00"},
    {"name": "Jalan Sultan Ismail", "code": "JLNSULTAN", "from": "KLCC", "to": "CHWKIT", "distance_km": 3, "free_flow_speed_kmh": 40, "capacity_vph": 3800, "daily_volume": 72000, "is_tolled": False, "toll_rate": "0.00"},
    {"name": "SPRINT Highway", "code": "SPRINT", "from": "KLCC", "to": "DMSRA", "distance_km": 12, "free_flow_speed_kmh": 80, "capacity_vph": 7500, "daily_volume": 180000, "is_tolled": True, "toll_rate": "1.60"},
    {"name": "Federal Highway", "code": "FEDHWY", "from": "KLSNTRL", "to": "PJ", "distance_km": 15, "free_flow_speed_kmh": 80, "capacity_vph": 12500, "daily_volume": 300000, "is_tolled": False, "toll_rate": "0.00"},
    {"name": "Federal Highway South", "code": "FEDHWYS", "from": "KLSNTRL", "to": "SUBANG", "distance_km": 22, "free_flow_speed_kmh": 80, "capacity_vph": 12500, "daily_volume": 280000, "is_tolled": False, "toll_rate": "0.00"},
    {"name": "NKVE", "code": "NKVE", "from": "DMSRA", "to": "SUBANG", "distance_km": 18, "free_flow_speed_kmh": 100, "capacity_vph": 8500, "daily_volume": 200000, "is_tolled": True, "toll_rate": "2.50"},
    {"name": "LDP Highway", "code": "LDP", "from": "DMSRA", "to": "PUCHONG", "distance_km": 25, "free_flow_speed_kmh": 90, "capacity_vph": 11500, "daily_volume": 275000, "is_tolled": True, "toll_rate": "2.10"},
    {"name": "Federal Highway West", "code": "FEDHWYW", "from": "SUBANG", "to": "SHAHALAM", "distance_km": 12, "free_flow_speed_kmh": 80, "capacity_vph": 10000, "daily_volume": 220000, "is_tolled": False, "toll_rate": "0.00"},
    {"name": "Jalan Kapar", "code": "JLNKAPAR", "from": "SHAHALAM", "to": "KLANG", "distance_km": 15, "free_flow_speed_kmh": 60, "capacity_vph": 5000, "daily_volume": 120000, "is_tolled": False, "toll_rate": "0.00"},
    {"name": "MRR2", "code": "MRR2", "from": "CHERAS", "to": "KLCC", "distance_km": 16, "free_flow_speed_kmh": 70, "capacity_vph": 8000, "daily_volume": 200000, "is_tolled": False, "toll_rate": "0.00"},
    {"name": "Ampang-KL Elevated", "code": "AMPKL", "from": "AMPANG", "to": "KLCC", "distance_km": 8, "free_flow_speed_kmh": 60, "capacity_vph": 5500, "daily_volume": 130000, "is_tolled": False, "toll_rate": "0.00"},
    {"name": "Penchala Link", "code": "PENCHALA", "from": "MNTKRA", "to": "DMSRA", "distance_km": 6, "free_flow_speed_kmh": 80, "capacity_vph": 4000, "daily_volume": 95000, "is_tolled": True, "toll_rate": "1.50"},
    {"name": "LDP South", "code": "LDPS", "from": "PUCHONG", "to": "PJ", "distance_km": 10, "free_flow_speed_kmh": 80, "capacity_vph": 9000, "daily_volume": 210000, "is_tolled": True, "toll_rate": "1.60"},
    {"name": "Jalan Duta", "code": "JLNDUTA", "from": "KEPONG", "to": "CHWKIT", "distance_km": 8, "free_flow_speed_kmh": 60, "capacity_vph": 6500, "daily_volume": 155000, "is_tolled": False, "toll_rate": "0.00"},
    {"name": "MEX Expressway", "code": "MEX", "from": "PTRJAYA", "to": "KLSNTRL", "distance_km": 28, "free_flow_speed_kmh": 100, "capacity_vph": 6200, "daily_volume": 140000, "is_tolled": True, "toll_rate": "3.00"},
    {"name": "Cyberjaya Road", "code": "CYBERRD", "from": "CYBER", "to": "PUCHONG", "distance_km": 12, "free_flow_speed_kmh": 80, "capacity_vph": 4000, "daily_volume": 85000, "is_tolled": False, "toll_rate": "0.00"},
    {"name": "DUKE Highway", "code": "DUKE", "from": "STPK", "to": "CHWKIT", "distance_km": 10, "free_flow_speed_kmh": 80, "capacity_vph": 8500, "daily_volume": 200000, "is_tolled": True, "toll_rate": "3.20"},
    {"name": "Jalan Imbi", "code": "JLNIMBI", "from": "BKTBNTG", "to": "KLCC", "distance_km": 2, "free_flow_speed_kmh": 30, "capacity_vph": 3000, "daily_volume": 55000, "is_tolled": False, "toll_rate": "0.00"},
    {"name": "Jalan PJ Utama", "code": "JLNPJ", "from": "PJ", "to": "BKTBNTG", "distance_km": 14, "free_flow_speed_kmh": 60, "capacity_vph": 6000, "daily_volume": 145000, "is_tolled": False, "toll_rate": "0.00"},
    {"name": "KESAS Highway", "code": "KESAS", "from": "SHAHALAM", "to": "PUCHONG", "distance_km": 15, "free_flow_speed_kmh": 90, "capacity_vph": 9000, "daily_volume": 200000, "is_tolled": True, "toll_rate": "1.80"},
    {"name": "Bangsar-Sentral", "code": "BNGSRKTM", "from": "BNGSR", "to": "KLSNTRL", "distance_km": 3, "free_flow_speed_kmh": 40, "capacity_vph": 3500, "daily_volume": 65000, "is_tolled": False, "toll_rate": "0.00"},
    {"name": "Kajang-Cheras Link", "code": "KJGCHRS", "from": "KAJANG", "to": "CHERAS", "distance_km": 12, "free_flow_speed_kmh": 70, "capacity_vph": 5500, "daily_volume": 130000, "is_tolled": False, "toll_rate": "0.00"},
]

TRANSIT_LINES = [
    {"code": "KJL", "name": "Kelana Jaya Line", "mode": "LRT", "route_description": "Putra Heights - Gombak", "capacity_per_hour": 8000, "frequency_minutes": 3.5, "color": "#e63946", "zones": ["SUBANG", "PJ", "KLSNTRL", "KLCC", "DMSRA"]},
    {"code": "APL", "name": "Ampang Line", "mode": "LRT", "route_description": "Putra Heights - Ampang", "capacity_per_hour": 6000, "frequency_minutes": 4.0, "color": "#2196f3", "zones": ["SUBANG", "PJ", "KLSNTRL", "AMPANG", "CHERAS"]},
    {"code": "MRT1", "name": "MRT Kajang Line", "mode": "MRT", "route_description": "Kwasa Damansara - Kajang", "capacity_per_hour": 12000, "frequency_minutes": 3.0, "color": "#4caf50", "zones": ["DMSRA", "BKTBNTG", "KLCC", "CHERAS", "KAJANG"]},
    {"code": "MRT2", "name": "MRT Putrajaya Line", "mode": "MRT", "route_description": "Kwasa Damansara - Putrajaya", "capacity_per_hour": 10000, "frequency_minutes": 4.0, "color": "#9c27b0", "zones": ["DMSRA", "KLSNTRL", "BNGSR", "CYBER", "PTRJAYA"]},
    {"code": "BRT1", "name": "Sunway BRT", "mode": "BRT", "route_description": "Sunway - Setia Jaya", "capacity_per_hour": 3000, "frequency_minutes": 5.0, "color": "#ff9800", "zones": ["SUBANG", "PJ", "BDRUTM"]},
    {"code": "KTM", "name": "KTM Komuter", "mode": "KTM", "route_description": "Tanjung Malim - Sungai Gadut", "capacity_per_hour": 5000, "frequency_minutes": 15.0, "color": "#795548", "zones": ["KLANG", "SHAHALAM", "SUBANG", "KLSNTRL", "BNGSR"]},
    {"code": "MONO", "name": "KL Monorail", "mode": "MNR", "route_description": "KL Sentral - Titiwangsa", "capacity_per_hour": 4000, "frequency_minutes": 4.0, "color": "#607d8b", "zones": ["KLSNTRL", "BKTBNTG", "CHWKIT"]},
    {"code": "RBUS", "name": "RapidKL Bus Network", "mode": "BUS", "route_description": "KL-wide coverage", "capacity_per_hour": 15000, "frequency_minutes": 10.0, "color": "#f44336", "zones": ["KLCC", "KLSNTRL", "BKTBNTG", "PJ", "SUBANG", "SHAHALAM", "CHERAS", "PUCHONG", "AMPANG", "KEPONG"]},
]

CARPOOL_HUBS = [
    {"name": "Subang Parade P&R", "zone_code": "SUBANG", "map_x": 0.12, "map_y": 0.58, "capacity": 80},
    {"name": "IOI City Mall P&R", "zone_code": "PTRJAYA", "map_x": 0.38, "map_y": 0.88, "capacity": 100},
    {"name": "Sunway Velocity Hub", "zone_code": "CHERAS", "map_x": 0.58, "map_y": 0.68, "capacity": 60},
    {"name": "Tropicana Gardens", "zone_code": "DMSRA", "map_x": 0.22, "map_y": 0.28, "capacity": 50},
    {"name": "Paradigm Mall PJ", "zone_code": "PJ", "map_x": 0.20, "map_y": 0.62, "capacity": 70},
    {"name": "Aeon Shah Alam", "zone_code": "SHAHALAM", "map_x": 0.10, "map_y": 0.70, "capacity": 90},
    {"name": "Setia City Mall", "zone_code": "SHAHALAM", "map_x": 0.06, "map_y": 0.74, "capacity": 60},
    {"name": "KL Sentral Hub", "zone_code": "KLSNTRL", "map_x": 0.44, "map_y": 0.53, "capacity": 120},
]

MODAL_SPLITS = [
    {"mode": "CAR", "share_pct": 67.0, "avg_occupancy": 1.2, "co2_grams_per_km": 171.0},
    {"mode": "MCY", "share_pct": 17.0, "avg_occupancy": 1.0, "co2_grams_per_km": 72.0},
    {"mode": "PUB", "share_pct": 12.0, "avg_occupancy": 40.0, "co2_grams_per_km": 30.0},
    {"mode": "EHL", "share_pct": 4.0, "avg_occupancy": 1.3, "co2_grams_per_km": 171.0},
]

COMPANIES = [
    {"name": "Petronas", "code": "PETRONAS", "sector": "Energy", "total_staff": 3200, "office_zone": "KLCC", "is_glc": True, "default_start_time": "08:00", "wfh_days_per_week": 2},
    {"name": "Maybank", "code": "MAYBANK", "sector": "Banking", "total_staff": 2800, "office_zone": "KLSNTRL", "is_glc": True, "default_start_time": "08:00", "wfh_days_per_week": 1},
    {"name": "CIMB Group", "code": "CIMB", "sector": "Banking", "total_staff": 2400, "office_zone": "KLSNTRL", "is_glc": True, "default_start_time": "08:30", "wfh_days_per_week": 2},
    {"name": "Telekom Malaysia", "code": "TM", "sector": "Telecom", "total_staff": 1900, "office_zone": "KLCC", "is_glc": True, "default_start_time": "08:00", "wfh_days_per_week": 2},
    {"name": "AirAsia Group", "code": "AIRASIA", "sector": "Aviation", "total_staff": 1600, "office_zone": "SUBANG", "is_glc": False, "default_start_time": "07:00", "wfh_days_per_week": 1},
    {"name": "Maxis Berhad", "code": "MAXIS", "sector": "Telecom", "total_staff": 1200, "office_zone": "KLCC", "is_glc": False, "default_start_time": "09:00", "wfh_days_per_week": 3},
    {"name": "Public Bank", "code": "PUBBANK", "sector": "Banking", "total_staff": 1800, "office_zone": "KLCC", "is_glc": False, "default_start_time": "08:00", "wfh_days_per_week": 1},
    {"name": "Sime Darby", "code": "SIMEDRBY", "sector": "Conglomerate", "total_staff": 980, "office_zone": "DMSRA", "is_glc": True, "default_start_time": "08:30", "wfh_days_per_week": 2},
    {"name": "Tenaga Nasional", "code": "TNB", "sector": "Energy", "total_staff": 2100, "office_zone": "BNGSR", "is_glc": True, "default_start_time": "08:00", "wfh_days_per_week": 1},
    {"name": "Axiata Group", "code": "AXIATA", "sector": "Telecom", "total_staff": 1400, "office_zone": "KLCC", "is_glc": True, "default_start_time": "09:00", "wfh_days_per_week": 2},
    {"name": "RHB Bank", "code": "RHB", "sector": "Banking", "total_staff": 1600, "office_zone": "KLSNTRL", "is_glc": False, "default_start_time": "08:00", "wfh_days_per_week": 1},
    {"name": "Hong Leong Bank", "code": "HLBANK", "sector": "Banking", "total_staff": 1200, "office_zone": "DMSRA", "is_glc": False, "default_start_time": "08:30", "wfh_days_per_week": 1},
    {"name": "Astro Malaysia", "code": "ASTRO", "sector": "Media", "total_staff": 850, "office_zone": "BDRUTM", "is_glc": True, "default_start_time": "09:00", "wfh_days_per_week": 3},
    {"name": "Sapura Energy", "code": "SAPURA", "sector": "Energy", "total_staff": 750, "office_zone": "KLCC", "is_glc": False, "default_start_time": "08:00", "wfh_days_per_week": 2},
    {"name": "JPM Government", "code": "JPM", "sector": "Government", "total_staff": 3500, "office_zone": "PTRJAYA", "is_glc": True, "default_start_time": "08:00", "wfh_days_per_week": 1},
    {"name": "MOF", "code": "MOF", "sector": "Government", "total_staff": 2200, "office_zone": "PTRJAYA", "is_glc": True, "default_start_time": "08:00", "wfh_days_per_week": 1},
    {"name": "MDEC", "code": "MDEC", "sector": "Technology", "total_staff": 450, "office_zone": "CYBER", "is_glc": True, "default_start_time": "09:00", "wfh_days_per_week": 3},
    {"name": "Grab Malaysia", "code": "GRAB", "sector": "Technology", "total_staff": 800, "office_zone": "DMSRA", "is_glc": False, "default_start_time": "10:00", "wfh_days_per_week": 3},
    {"name": "Shopee Malaysia", "code": "SHOPEE", "sector": "Technology", "total_staff": 1100, "office_zone": "BKTBNTG", "is_glc": False, "default_start_time": "10:00", "wfh_days_per_week": 3},
    {"name": "Digi Telecommunications", "code": "DIGI", "sector": "Telecom", "total_staff": 1300, "office_zone": "SHAHALAM", "is_glc": False, "default_start_time": "08:30", "wfh_days_per_week": 2},
    {"name": "Gamuda Berhad", "code": "GAMUDA", "sector": "Construction", "total_staff": 900, "office_zone": "PJ", "is_glc": False, "default_start_time": "07:30", "wfh_days_per_week": 1},
    {"name": "UEM Sunrise", "code": "UEM", "sector": "Construction", "total_staff": 650, "office_zone": "MNTKRA", "is_glc": True, "default_start_time": "08:00", "wfh_days_per_week": 1},
    {"name": "Khazanah Nasional", "code": "KHZNH", "sector": "Government", "total_staff": 380, "office_zone": "KLCC", "is_glc": True, "default_start_time": "09:00", "wfh_days_per_week": 2},
    {"name": "Bank Negara Malaysia", "code": "BNM", "sector": "Government", "total_staff": 1800, "office_zone": "KLSNTRL", "is_glc": True, "default_start_time": "08:30", "wfh_days_per_week": 1},
    {"name": "Proton Holdings", "code": "PROTON", "sector": "Manufacturing", "total_staff": 1200, "office_zone": "SHAHALAM", "is_glc": True, "default_start_time": "07:00", "wfh_days_per_week": 0},
]


class Command(BaseCommand):
    help = "Seed all KL reference data, companies, and one pre-computed simulation run."

    def handle(self, *args, **options):
        logger.info("Starting seed_kl_data command")
        self.stdout.write("Seeding MyCommute KL reference data...")

        zone_map = self._seed_zones()
        corridor_map = self._seed_corridors(zone_map)
        self._seed_transit_lines(zone_map)
        self._seed_carpool_hubs(zone_map)
        self._seed_modal_splits()
        company_map = self._seed_companies(zone_map)
        sim_run = self._seed_simulation_run()
        self._seed_corridor_time_slices(sim_run, corridor_map)
        self._seed_company_sim_results(sim_run, company_map)

        self.stdout.write(self.style.SUCCESS("All seed data loaded successfully."))
        logger.info("seed_kl_data command completed successfully")

    # ------------------------------------------------------------------
    # Zones
    # ------------------------------------------------------------------
    def _seed_zones(self):
        """Create or update all 20 KV zones. Returns dict of code -> Zone instance."""
        zone_map = {}
        created_count = 0
        for z in ZONES:
            obj, created = Zone.objects.get_or_create(
                code=z["code"],
                defaults={
                    "name": z["name"],
                    "map_x": z["map_x"],
                    "map_y": z["map_y"],
                    "is_major": z["is_major"],
                    "icon": z["icon"],
                    "population": z["population"],
                },
            )
            zone_map[z["code"]] = obj
            if created:
                created_count += 1
                logger.debug("Created zone: %s (%s)", z["name"], z["code"])

        self.stdout.write(
            self.style.SUCCESS(f"  Zones: {created_count} created, {len(ZONES) - created_count} already existed")
        )
        logger.info("Seeded %d zones (%d new)", len(ZONES), created_count)
        return zone_map

    # ------------------------------------------------------------------
    # Corridors
    # ------------------------------------------------------------------
    def _seed_corridors(self, zone_map):
        """Create or update all 22 corridors. Returns dict of code -> Corridor instance."""
        corridor_map = {}
        created_count = 0
        for c in CORRIDORS:
            obj, created = Corridor.objects.get_or_create(
                code=c["code"],
                defaults={
                    "name": c["name"],
                    "zone_from": zone_map[c["from"]],
                    "zone_to": zone_map[c["to"]],
                    "distance_km": c["distance_km"],
                    "free_flow_speed_kmh": c["free_flow_speed_kmh"],
                    "capacity_vph": c["capacity_vph"],
                    "daily_volume": c["daily_volume"],
                    "is_tolled": c["is_tolled"],
                    "toll_rate": Decimal(c["toll_rate"]),
                },
            )
            corridor_map[c["code"]] = obj
            if created:
                created_count += 1
                logger.debug("Created corridor: %s (%s -> %s)", c["name"], c["from"], c["to"])

        self.stdout.write(
            self.style.SUCCESS(f"  Corridors: {created_count} created, {len(CORRIDORS) - created_count} already existed")
        )
        logger.info("Seeded %d corridors (%d new)", len(CORRIDORS), created_count)
        return corridor_map

    # ------------------------------------------------------------------
    # Transit lines
    # ------------------------------------------------------------------
    def _seed_transit_lines(self, zone_map):
        """Create or update all 8 transit lines with zone associations."""
        created_count = 0
        for t in TRANSIT_LINES:
            obj, created = TransitLine.objects.get_or_create(
                code=t["code"],
                defaults={
                    "name": t["name"],
                    "mode": t["mode"],
                    "capacity_per_hour": t["capacity_per_hour"],
                    "frequency_minutes": t["frequency_minutes"],
                    "color": t["color"],
                    "route_description": t["route_description"],
                },
            )
            if created:
                created_count += 1
                logger.debug("Created transit line: %s (%s)", t["name"], t["code"])

            # Always set zones (M2M is idempotent via set())
            zone_objs = [zone_map[zc] for zc in t["zones"]]
            obj.zones_served.set(zone_objs)

        self.stdout.write(
            self.style.SUCCESS(
                f"  Transit lines: {created_count} created, {len(TRANSIT_LINES) - created_count} already existed"
            )
        )
        logger.info("Seeded %d transit lines (%d new)", len(TRANSIT_LINES), created_count)

    # ------------------------------------------------------------------
    # Carpool hubs
    # ------------------------------------------------------------------
    def _seed_carpool_hubs(self, zone_map):
        """Create or update all 8 carpool hubs."""
        created_count = 0
        for h in CARPOOL_HUBS:
            _, created = CarpoolHub.objects.get_or_create(
                name=h["name"],
                defaults={
                    "zone": zone_map[h["zone_code"]],
                    "map_x": h["map_x"],
                    "map_y": h["map_y"],
                    "capacity": h["capacity"],
                },
            )
            if created:
                created_count += 1
                logger.debug("Created carpool hub: %s in %s", h["name"], h["zone_code"])

        self.stdout.write(
            self.style.SUCCESS(
                f"  Carpool hubs: {created_count} created, {len(CARPOOL_HUBS) - created_count} already existed"
            )
        )
        logger.info("Seeded %d carpool hubs (%d new)", len(CARPOOL_HUBS), created_count)

    # ------------------------------------------------------------------
    # Modal splits
    # ------------------------------------------------------------------
    def _seed_modal_splits(self):
        """Create or update the 4 modal split records."""
        created_count = 0
        for m in MODAL_SPLITS:
            _, created = ModalSplit.objects.get_or_create(
                mode=m["mode"],
                defaults={
                    "share_pct": m["share_pct"],
                    "avg_occupancy": m["avg_occupancy"],
                    "co2_grams_per_km": m["co2_grams_per_km"],
                },
            )
            if created:
                created_count += 1
                logger.debug("Created modal split: %s (%.0f%%)", m["mode"], m["share_pct"])

        self.stdout.write(
            self.style.SUCCESS(
                f"  Modal splits: {created_count} created, {len(MODAL_SPLITS) - created_count} already existed"
            )
        )
        logger.info("Seeded %d modal splits (%d new)", len(MODAL_SPLITS), created_count)

    # ------------------------------------------------------------------
    # Companies
    # ------------------------------------------------------------------
    def _seed_companies(self, zone_map):
        """Create or update all 25 companies. Returns dict of code -> Company instance."""
        company_map = {}
        created_count = 0
        for c in COMPANIES:
            h, m = c["default_start_time"].split(":")
            start_time = time(int(h), int(m))
            obj, created = Company.objects.get_or_create(
                code=c["code"],
                defaults={
                    "name": c["name"],
                    "sector": c["sector"],
                    "total_staff": c["total_staff"],
                    "office_zone": zone_map[c["office_zone"]],
                    "is_glc": c["is_glc"],
                    "default_start_time": start_time,
                    "wfh_days_per_week": c["wfh_days_per_week"],
                },
            )
            company_map[c["code"]] = obj
            if created:
                created_count += 1
                logger.debug(
                    "Created company: %s (%s), sector=%s, staff=%d",
                    c["name"], c["code"], c["sector"], c["total_staff"],
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"  Companies: {created_count} created, {len(COMPANIES) - created_count} already existed"
            )
        )
        logger.info("Seeded %d companies (%d new)", len(COMPANIES), created_count)
        return company_map

    # ------------------------------------------------------------------
    # Simulation run
    # ------------------------------------------------------------------
    def _seed_simulation_run(self):
        """Create the pre-computed pilot simulation run if it does not exist."""
        run_name = "KV Pilot Phase 1 \u2014 Feb 2026"
        run, created = SimulationRun.objects.get_or_create(
            name=run_name,
            defaults={
                "status": "CMP",
                "completed_at": timezone.now(),
                "enable_stagger": True,
                "enable_wfh": True,
                "enable_carpool": True,
                "enable_transit_boost": True,
                "stagger_window_start": time(7, 0),
                "stagger_window_end": time(10, 30),
                "wfh_max_days": 2,
                "wfh_sector_cap_pct": 40,
                "carpool_max_detour_km": 5.0,
                "transit_frequency_boost_pct": 20,
                "peak_congestion_before": 0.87,
                "peak_congestion_after": 0.38,
                "avg_commute_before": 68.0,
                "avg_commute_after": 29.0,
                "peak_vehicles_before": 284000,
                "peak_vehicles_after": 178000,
                "co2_saved_tonnes": 412.0,
                "total_carpool_groups": 186,
                "total_wfh_today": 14200,
            },
        )

        status_label = "created" if created else "already existed"
        self.stdout.write(self.style.SUCCESS(f"  SimulationRun '{run_name}': {status_label}"))
        logger.info("SimulationRun '%s' %s (id=%d)", run_name, status_label, run.pk)
        return run

    # ------------------------------------------------------------------
    # Corridor time slices (bulk generation)
    # ------------------------------------------------------------------
    def _seed_corridor_time_slices(self, sim_run, corridor_map):
        """
        Generate 22 corridors x 64 time slots x 2 scenarios = 2816 CorridorTimeSlice records.

        Before scenario: tight Gaussian centered at 08:00, std_dev=0.75h
        After scenario: flatter Gaussian shifted to 08:45, std_dev=1.5h

        Uses BPR function to compute travel times from volume and capacity.
        Skips generation if records already exist for this run.
        """
        existing_count = CorridorTimeSlice.objects.filter(simulation_run=sim_run).count()
        if existing_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  CorridorTimeSlice: {existing_count} records already exist for this run, skipping"
                )
            )
            logger.info(
                "Skipping CorridorTimeSlice generation: %d records already exist for run id=%d",
                existing_count, sim_run.pk,
            )
            return

        # Build 64 time slots from 06:00 to 21:45 in 15-min increments
        time_slots = []
        for i in range(64):
            total_minutes = 6 * 60 + i * 15
            hour = total_minutes // 60
            minute = total_minutes % 60
            time_slots.append({
                "label": f"{hour:02d}:{minute:02d}",
                "hour_float": total_minutes / 60.0,
            })

        logger.info(
            "Generating CorridorTimeSlice records: %d corridors x %d slots x 2 scenarios",
            len(corridor_map), len(time_slots),
        )

        # Gaussian parameters for each scenario
        scenarios = {
            "before": {"mean_hour": 8.0, "std_dev": 0.75},
            "after": {"mean_hour": 8.75, "std_dev": 1.5},
        }

        records = []
        for corridor_data in CORRIDORS:
            corridor = corridor_map[corridor_data["code"]]
            daily_vol = corridor.daily_volume
            capacity_vph = corridor.capacity_vph
            distance_km = corridor.distance_km
            free_flow_speed = corridor.free_flow_speed_kmh
            free_flow_time_min = (distance_km / free_flow_speed) * 60.0

            for scenario_key, params in scenarios.items():
                # Compute Gaussian weights for all time slots
                weights = []
                for slot in time_slots:
                    h = slot["hour_float"]
                    diff = (h - params["mean_hour"]) / params["std_dev"]
                    weights.append(math.exp(-0.5 * diff * diff))

                weight_sum = sum(weights)
                if weight_sum < 1e-12:
                    # Fallback: uniform distribution (should not happen with given params)
                    weights = [1.0 / len(time_slots)] * len(time_slots)
                    weight_sum = 1.0

                for idx, slot in enumerate(time_slots):
                    # Proportion of daily traffic in this 15-min slot
                    proportion = weights[idx] / weight_sum
                    volume = int(round(daily_vol * proportion))

                    volume_car = int(round(volume * 0.67))
                    volume_motorcycle = int(round(volume * 0.17))

                    # Capacity for a 15-min slot is 1/4 of hourly capacity
                    capacity_15min = capacity_vph / 4.0
                    capacity_ratio = volume / capacity_15min if capacity_15min > 0 else 0.0

                    # BPR travel time: t = t0 * (1 + 0.15 * (V/C)^4)
                    bpr_factor = 1.0 + 0.15 * (capacity_ratio ** 4)
                    travel_time_min = free_flow_time_min * bpr_factor

                    # Speed from travel time
                    speed_kmh = (distance_km / travel_time_min * 60.0) if travel_time_min > 0 else 0.0

                    # Congestion level capped at 1.0
                    congestion_level = min(capacity_ratio, 1.0)

                    records.append(
                        CorridorTimeSlice(
                            simulation_run=sim_run,
                            corridor=corridor,
                            time_slot=slot["label"],
                            scenario=scenario_key,
                            volume=volume,
                            volume_car=volume_car,
                            volume_motorcycle=volume_motorcycle,
                            capacity_ratio=round(capacity_ratio, 4),
                            travel_time_min=round(travel_time_min, 2),
                            speed_kmh=round(speed_kmh, 1),
                            congestion_level=round(congestion_level, 4),
                        )
                    )

        # Bulk create in batches for better memory handling
        batch_size = 500
        total_created = 0
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            CorridorTimeSlice.objects.bulk_create(batch)
            total_created += len(batch)
            logger.debug(
                "CorridorTimeSlice bulk_create batch: %d/%d records",
                total_created, len(records),
            )

        self.stdout.write(self.style.SUCCESS(f"  CorridorTimeSlice: {total_created} records created"))
        logger.info("Created %d CorridorTimeSlice records for run id=%d", total_created, sim_run.pk)

    # ------------------------------------------------------------------
    # Company simulation results
    # ------------------------------------------------------------------
    def _seed_company_sim_results(self, sim_run, company_map):
        """
        Create CompanySimResult for each of the 25 companies.

        Computes staggered start times, WFH/carpool counts, and load contribution.
        """
        existing_count = CompanySimResult.objects.filter(simulation_run=sim_run).count()
        if existing_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  CompanySimResult: {existing_count} records already exist for this run, skipping"
                )
            )
            logger.info(
                "Skipping CompanySimResult generation: %d records exist for run id=%d",
                existing_count, sim_run.pk,
            )
            return

        # Sort companies by staff size (descending) for stagger assignment.
        # Larger companies get the most spread across the 07:00-10:30 window.
        sorted_companies = sorted(COMPANIES, key=lambda c: c["total_staff"], reverse=True)

        # Stagger window: 07:00 to 10:30 (3.5 hours = 210 minutes)
        stagger_start_minutes = 7 * 60  # 420
        stagger_end_minutes = 10 * 60 + 30  # 630
        stagger_range = stagger_end_minutes - stagger_start_minutes  # 210
        num_companies = len(sorted_companies)

        # Compute total staff across all companies for load_contribution
        total_all_staff_on_road = 0
        company_results_data = []

        for idx, c_data in enumerate(sorted_companies):
            company = company_map[c_data["code"]]
            total_staff = c_data["total_staff"]

            # Distribute start times evenly across the stagger window
            offset_minutes = int(stagger_range * idx / max(num_companies - 1, 1))
            assigned_minutes = stagger_start_minutes + offset_minutes
            assigned_start = time(assigned_minutes // 60, assigned_minutes % 60)

            # Staff on road before: 85% commute during peak
            staff_on_road_before = int(round(total_staff * 0.85))

            # WFH count: total_staff * (wfh_days/5) * 0.8 eligibility
            wfh_days = c_data["wfh_days_per_week"]
            wfh_count = int(round(total_staff * (wfh_days / 5.0) * 0.8))

            # Carpool count: 12% uptake
            carpool_count = int(round(total_staff * 0.12))

            # Staff on road after: reduce by WFH + carpool savings
            # Carpool saves roughly half the vehicles (2 people per car instead of 1)
            carpool_vehicle_savings = int(round(carpool_count * 0.5))
            staff_on_road_after = max(
                staff_on_road_before - wfh_count - carpool_vehicle_savings, 0
            )

            total_all_staff_on_road += staff_on_road_before

            company_results_data.append({
                "company": company,
                "assigned_start_time": assigned_start,
                "staff_on_road_before": staff_on_road_before,
                "staff_on_road_after": staff_on_road_after,
                "wfh_count": wfh_count,
                "carpool_count": carpool_count,
            })

        # Compute load_contribution and build ORM objects
        results = []
        for data in company_results_data:
            load_contribution = (
                data["staff_on_road_before"] / total_all_staff_on_road
                if total_all_staff_on_road > 0 else 0.0
            )
            results.append(
                CompanySimResult(
                    simulation_run=sim_run,
                    company=data["company"],
                    assigned_start_time=data["assigned_start_time"],
                    staff_on_road_before=data["staff_on_road_before"],
                    staff_on_road_after=data["staff_on_road_after"],
                    wfh_count=data["wfh_count"],
                    carpool_count=data["carpool_count"],
                    load_contribution=round(load_contribution, 4),
                )
            )
            logger.debug(
                "CompanySimResult: %s start=%s, before=%d, after=%d, wfh=%d, carpool=%d, load=%.4f",
                data["company"].code,
                data["assigned_start_time"],
                data["staff_on_road_before"],
                data["staff_on_road_after"],
                data["wfh_count"],
                data["carpool_count"],
                load_contribution,
            )

        CompanySimResult.objects.bulk_create(results)
        self.stdout.write(self.style.SUCCESS(f"  CompanySimResult: {len(results)} records created"))
        logger.info("Created %d CompanySimResult records for run id=%d", len(results), sim_run.pk)
