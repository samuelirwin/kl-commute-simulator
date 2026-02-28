"""
Simulation engine package.

Algorithm modules for the MyCommute KL commute optimization system:
- bpr: BPR volume-delay travel time function
- demand: Gaussian departure demand profile generator
- stagger: Staggered working hours optimizer (SLSQP)
- wfh: Work-From-Home rotation planner
- carpool: Carpool group matching engine
- co2: CO2 emission reduction calculator
- traffic_sim: Mesoscopic time-sliced traffic simulator
- runner: Orchestrator that wires all algorithms into a simulation pipeline
"""
