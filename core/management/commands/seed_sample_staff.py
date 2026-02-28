"""
Management command to seed ~1,250 sample staff members with realistic Malaysian names.

Creates 50 StaffMember records per company (25 companies), assigns departments,
home zones, transport modes, and generates StaffSchedule records for the existing
pre-computed SimulationRun.
"""
import logging
import math
import random
from datetime import time

from django.core.management.base import BaseCommand

from company.models import Company, Department, StaffMember, StaffSchedule
from core.models import Zone
from simulation.models import CompanySimResult, SimulationRun

logger = logging.getLogger("core")

STAFF_PER_COMPANY = 50

# ---------------------------------------------------------------------------
# Malaysian name pools by ethnicity
# ---------------------------------------------------------------------------

MALAY_FIRST_MALE = [
    "Ahmad", "Muhammad", "Mohd", "Ali", "Hassan",
    "Ibrahim", "Ismail", "Faizal", "Azman", "Rizal",
    "Hafiz", "Amir", "Nazri", "Zulkifli", "Ramli",
]
MALAY_FIRST_FEMALE = [
    "Siti", "Nurul", "Fatimah", "Aisyah", "Nur",
    "Farah", "Zahra", "Aminah", "Norliza", "Haslinda",
]
MALAY_PATRONYMICS = [
    "Abdullah", "Rahman", "Hassan", "Ismail", "Ahmad",
    "Yusof", "Omar", "Ali", "Hussain", "Karim",
]

CHINESE_FIRST = [
    "Wei Jie", "Kai Wen", "Jun Hao", "Zhi Wei", "Yi Xuan",
    "Mei Ling", "Shu Ting", "Xin Yi", "Jia Min", "Li Hua",
    "Chun Keat", "Wai Keong", "Boon Keng", "Siew Lian", "Pei Shan",
]
CHINESE_SURNAMES = [
    "Tan", "Lim", "Wong", "Ng", "Lee",
    "Chan", "Chong", "Ong", "Yap", "Goh",
    "Low", "Koh", "Foo", "Teo", "Sim",
]

INDIAN_FIRST_MALE = [
    "Rajesh", "Suresh", "Dinesh", "Ganesh", "Vikram",
    "Kumar", "Ravi", "Muthu", "Selvan",
]
INDIAN_FIRST_FEMALE = [
    "Priya", "Lakshmi", "Deepa", "Anita", "Nirmala", "Kamala",
]
INDIAN_SURNAMES = [
    "Pillai", "Nair", "Menon", "Krishnan", "Muthu",
    "Rajan", "Kumar", "Subramaniam", "Sharma", "Patel",
]

# Home zone weights by zone code (sums to 100%)
HOME_ZONE_WEIGHTS = {
    "SUBANG": 0.12, "PJ": 0.12, "SHAHALAM": 0.10, "CHERAS": 0.10,
    "PUCHONG": 0.08, "KLANG": 0.08, "KAJANG": 0.07, "KEPONG": 0.05,
    "STPK": 0.04, "AMPANG": 0.04, "BNGSR": 0.03, "MNTKRA": 0.03,
    "BDRUTM": 0.03, "KLCC": 0.02, "KLSNTRL": 0.02, "BKTBNTG": 0.02,
    "CHWKIT": 0.01, "CYBER": 0.02, "PTRJAYA": 0.01, "DMSRA": 0.01,
}

# Transport mode distribution
TRANSPORT_WEIGHTS = [
    ("CAR", 0.67),
    ("MCY", 0.17),
    ("PUB", 0.12),
    ("EHL", 0.04),
]

# Department template: (name, share_pct)
DEPARTMENTS = [
    ("Operations", 0.30),
    ("Corporate/Admin", 0.35),
    ("Technology/IT", 0.35),
]

# WFH day assignments per company, spread across the week.
# Key = wfh_days_per_week, Value = list of day indices (0=Mon to 4=Fri)
WFH_DAY_PATTERNS = {
    0: [],
    1: [[1], [3], [0], [2], [4]],
    2: [[1, 3], [0, 2], [2, 4], [0, 3], [1, 4]],
    3: [[0, 2, 4], [1, 3, 4], [0, 1, 3], [0, 2, 3], [1, 2, 4]],
}


class Command(BaseCommand):
    help = "Seed ~1,250 sample staff members with realistic Malaysian names and schedules."

    def handle(self, *args, **options):
        logger.info("Starting seed_sample_staff command")
        self.stdout.write("Seeding sample staff members...")

        # Validate prerequisite data exists
        companies = list(Company.objects.select_related("office_zone").order_by("code"))
        if not companies:
            self.stderr.write(self.style.ERROR(
                "No companies found. Run 'seed_kl_data' first."
            ))
            logger.error("seed_sample_staff aborted: no companies in database")
            return

        zones = {z.code: z for z in Zone.objects.all()}
        if not zones:
            self.stderr.write(self.style.ERROR(
                "No zones found. Run 'seed_kl_data' first."
            ))
            logger.error("seed_sample_staff aborted: no zones in database")
            return

        # Check if staff already exist (idempotency)
        existing_staff = StaffMember.objects.count()
        if existing_staff > 0:
            self.stdout.write(self.style.SUCCESS(
                f"  StaffMember: {existing_staff} records already exist, skipping staff creation"
            ))
            logger.info("Skipping staff creation: %d StaffMember records already exist", existing_staff)
        else:
            self._seed_departments(companies)
            self._seed_staff_members(companies, zones)

        # Create schedules if a completed simulation run exists
        self._seed_staff_schedules(companies)

        self.stdout.write(self.style.SUCCESS("Sample staff seeding completed successfully."))
        logger.info("seed_sample_staff command completed successfully")

    # ------------------------------------------------------------------
    # Departments
    # ------------------------------------------------------------------
    def _seed_departments(self, companies):
        """Create 3 departments per company using get_or_create."""
        created_count = 0
        for company in companies:
            for dept_name, share in DEPARTMENTS:
                staff_count = int(round(company.total_staff * share))

                # For Manufacturing sector, Operations cannot WFH
                can_wfh = True
                if company.sector == "Manufacturing" and dept_name == "Operations":
                    can_wfh = False

                _, created = Department.objects.get_or_create(
                    company=company,
                    name=dept_name,
                    defaults={
                        "staff_count": staff_count,
                        "can_wfh": can_wfh,
                    },
                )
                if created:
                    created_count += 1
                    logger.debug(
                        "Created department: %s - %s (staff=%d, can_wfh=%s)",
                        company.code, dept_name, staff_count, can_wfh,
                    )

        total_possible = len(companies) * len(DEPARTMENTS)
        self.stdout.write(
            self.style.SUCCESS(
                f"  Departments: {created_count} created, {total_possible - created_count} already existed"
            )
        )
        logger.info("Seeded departments: %d created out of %d total", created_count, total_possible)

    # ------------------------------------------------------------------
    # Staff members
    # ------------------------------------------------------------------
    def _seed_staff_members(self, companies, zones):
        """Generate 50 staff members per company with Malaysian names and attributes."""
        # Pre-compute home zone weighted selection list
        zone_codes = list(HOME_ZONE_WEIGHTS.keys())
        zone_weights = [HOME_ZONE_WEIGHTS[zc] for zc in zone_codes]

        # Pre-compute transport mode weighted selection list
        transport_modes = [t[0] for t in TRANSPORT_WEIGHTS]
        transport_weights = [t[1] for t in TRANSPORT_WEIGHTS]

        # Use a fixed seed for reproducibility
        rng = random.Random(42)

        all_staff = []
        for company in companies:
            departments = list(
                Department.objects.filter(company=company).order_by("name")
            )
            if not departments:
                logger.warning("No departments found for %s, skipping", company.code)
                continue

            # Build department assignment list matching the share percentages
            dept_assignments = []
            for dept in departments:
                for dept_template_name, share in DEPARTMENTS:
                    if dept.name == dept_template_name:
                        count = int(round(STAFF_PER_COMPANY * share))
                        dept_assignments.extend([dept] * count)
                        break

            # Pad or trim to exactly STAFF_PER_COMPANY
            while len(dept_assignments) < STAFF_PER_COMPANY:
                dept_assignments.append(rng.choice(departments))
            dept_assignments = dept_assignments[:STAFF_PER_COMPANY]
            rng.shuffle(dept_assignments)

            for seq_num in range(1, STAFF_PER_COMPANY + 1):
                idx = seq_num - 1
                dept = dept_assignments[idx]

                # Generate name based on ethnicity distribution
                name = self._generate_name(rng)

                # Home zone (weighted random)
                home_zone_code = rng.choices(zone_codes, weights=zone_weights, k=1)[0]
                home_zone = zones[home_zone_code]

                # Transport mode (weighted random)
                transport = rng.choices(transport_modes, weights=transport_weights, k=1)[0]

                # Vehicle ownership
                has_vehicle = transport in ("CAR", "MCY")

                # Willingness to carpool (35% of those with vehicles)
                willing_to_carpool = has_vehicle and rng.random() < 0.35

                # Carpool seats: 2 or 3 for willing drivers
                carpool_seats = rng.choice([2, 3]) if willing_to_carpool else 0

                # WFH eligibility: 80% true, 20% false
                can_wfh = rng.random() < 0.80
                # Override: Manufacturing Operations staff cannot WFH
                if company.sector == "Manufacturing" and dept.name == "Operations":
                    can_wfh = False

                employee_id = f"{company.code}-{seq_num:04d}"

                all_staff.append(
                    StaffMember(
                        employee_id=employee_id,
                        name=name,
                        company=company,
                        department=dept,
                        home_zone=home_zone,
                        primary_transport=transport,
                        has_vehicle=has_vehicle,
                        willing_to_carpool=willing_to_carpool,
                        carpool_seats=carpool_seats,
                        can_wfh=can_wfh,
                    )
                )

        # Bulk create in batches
        batch_size = 250
        total_created = 0
        for i in range(0, len(all_staff), batch_size):
            batch = all_staff[i:i + batch_size]
            StaffMember.objects.bulk_create(batch)
            total_created += len(batch)
            logger.debug("StaffMember bulk_create batch: %d/%d", total_created, len(all_staff))

        self.stdout.write(self.style.SUCCESS(f"  StaffMember: {total_created} records created"))
        logger.info("Created %d StaffMember records across %d companies", total_created, len(companies))

    # ------------------------------------------------------------------
    # Name generation
    # ------------------------------------------------------------------
    def _generate_name(self, rng):
        """
        Generate a realistic Malaysian name following demographic distribution:
        60% Malay, 25% Chinese, 15% Indian.
        """
        roll = rng.random()

        if roll < 0.60:
            # Malay name
            is_male = rng.random() < 0.5
            if is_male:
                first = rng.choice(MALAY_FIRST_MALE)
                patronymic = rng.choice(MALAY_PATRONYMICS)
                return f"{first} bin {patronymic}"
            else:
                first = rng.choice(MALAY_FIRST_FEMALE)
                patronymic = rng.choice(MALAY_PATRONYMICS)
                return f"{first} binti {patronymic}"

        elif roll < 0.85:
            # Chinese name
            surname = rng.choice(CHINESE_SURNAMES)
            given = rng.choice(CHINESE_FIRST)
            return f"{surname} {given}"

        else:
            # Indian name
            is_male = rng.random() < 0.6
            if is_male:
                first = rng.choice(INDIAN_FIRST_MALE)
            else:
                first = rng.choice(INDIAN_FIRST_FEMALE)
            surname = rng.choice(INDIAN_SURNAMES)
            return f"{first} {surname}"

    # ------------------------------------------------------------------
    # Staff schedules
    # ------------------------------------------------------------------
    def _seed_staff_schedules(self, companies):
        """
        Create StaffSchedule records for each staff member x 5 weekdays.

        Links to the existing completed SimulationRun. Assigns WFH days based
        on the company's policy, and estimates commute times based on
        zone-to-zone distance.
        """
        sim_run = SimulationRun.objects.filter(status="CMP").first()
        if not sim_run:
            self.stdout.write(self.style.WARNING(
                "  No completed SimulationRun found, skipping schedule generation"
            ))
            logger.warning("Skipping StaffSchedule: no completed SimulationRun")
            return

        # Check if schedules already exist for this run
        existing_count = StaffSchedule.objects.filter(simulation_run=sim_run).count()
        if existing_count > 0:
            self.stdout.write(self.style.SUCCESS(
                f"  StaffSchedule: {existing_count} records already exist for this run, skipping"
            ))
            logger.info(
                "Skipping StaffSchedule generation: %d records exist for run id=%d",
                existing_count, sim_run.pk,
            )
            return

        # Pre-fetch CompanySimResult for assigned start times
        sim_results = {
            csr.company_id: csr
            for csr in CompanySimResult.objects.filter(simulation_run=sim_run)
        }

        # Pre-fetch all zone coordinates for commute estimation
        zone_coords = {
            z.code: (z.map_x, z.map_y) for z in Zone.objects.all()
        }

        rng = random.Random(42)
        all_schedules = []
        staff_qs = StaffMember.objects.select_related("company", "home_zone").all()

        logger.info(
            "Generating StaffSchedule records for %d staff x 5 days, run id=%d",
            staff_qs.count(), sim_run.pk,
        )

        for staff in staff_qs:
            company = staff.company
            csr = sim_results.get(company.pk)
            assigned_start = csr.assigned_start_time if csr else company.default_start_time

            # Determine WFH days for this company
            wfh_days = self._get_wfh_days(company, rng)

            # Estimate commute time based on map distance
            commute_min = self._estimate_commute(
                staff.home_zone.code,
                company.office_zone.code if hasattr(company, "office_zone") else None,
                zone_coords,
            )

            # Departure window: assigned_start minus 30 minutes to assigned_start
            dep_start = self._subtract_minutes(assigned_start, 30)
            departure_window = f"{dep_start.strftime('%H:%M')} - {assigned_start.strftime('%H:%M')}"

            for day in range(5):  # 0=Mon to 4=Fri
                # Determine if WFH for this day
                is_wfh = staff.can_wfh and (day in wfh_days)
                location = "WFH" if is_wfh else "OFF"

                all_schedules.append(
                    StaffSchedule(
                        staff=staff,
                        simulation_run=sim_run,
                        day_of_week=day,
                        location=location,
                        assigned_start_time=assigned_start,
                        departure_window=departure_window if location == "OFF" else "",
                        estimated_commute_min=commute_min if location == "OFF" else 0.0,
                    )
                )

        # Bulk create in batches
        batch_size = 1000
        total_created = 0
        for i in range(0, len(all_schedules), batch_size):
            batch = all_schedules[i:i + batch_size]
            StaffSchedule.objects.bulk_create(batch)
            total_created += len(batch)
            logger.debug("StaffSchedule bulk_create batch: %d/%d", total_created, len(all_schedules))

        self.stdout.write(self.style.SUCCESS(f"  StaffSchedule: {total_created} records created"))
        logger.info("Created %d StaffSchedule records for run id=%d", total_created, sim_run.pk)

    # ------------------------------------------------------------------
    # Helper: determine WFH days for a company
    # ------------------------------------------------------------------
    def _get_wfh_days(self, company, rng):
        """
        Return a list of day-of-week indices (0-4) when a company's eligible
        staff work from home. Uses company code hash for consistent assignment.
        """
        wfh_count = company.wfh_days_per_week
        if wfh_count == 0:
            return []

        patterns = WFH_DAY_PATTERNS.get(wfh_count)
        if not patterns:
            # Fallback: pick random days for unsupported counts
            return sorted(rng.sample(range(5), min(wfh_count, 5)))

        # Use company code hash to select a consistent pattern
        pattern_idx = hash(company.code) % len(patterns)
        return patterns[pattern_idx]

    # ------------------------------------------------------------------
    # Helper: estimate commute time from map coordinates
    # ------------------------------------------------------------------
    def _estimate_commute(self, home_zone_code, office_zone_code, zone_coords):
        """
        Estimate commute time in minutes based on Euclidean distance between
        zone map coordinates. Maps distance to a 20-80 minute range.
        """
        if not office_zone_code or home_zone_code not in zone_coords or office_zone_code not in zone_coords:
            return 45.0  # Default mid-range commute

        hx, hy = zone_coords[home_zone_code]
        ox, oy = zone_coords[office_zone_code]
        distance = math.sqrt((hx - ox) ** 2 + (hy - oy) ** 2)

        # Max possible Euclidean distance on 0-1 map is ~1.41
        # Scale to 20-80 minute range
        min_commute = 20.0
        max_commute = 80.0
        max_distance = 1.0  # Practical maximum for KV zones

        normalized = min(distance / max_distance, 1.0)
        commute = min_commute + normalized * (max_commute - min_commute)

        return round(commute, 1)

    # ------------------------------------------------------------------
    # Helper: subtract minutes from a time object
    # ------------------------------------------------------------------
    @staticmethod
    def _subtract_minutes(t, minutes):
        """Subtract minutes from a time object, wrapping at midnight boundary."""
        total = t.hour * 60 + t.minute - minutes
        if total < 0:
            total += 24 * 60
        return time(total // 60, total % 60)
