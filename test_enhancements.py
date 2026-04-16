#!/usr/bin/env python3
"""Verification test for enhanced Sky Burrito modules."""

import sys

print('✓ Verifying enhanced modules...\n')

# Test 1: Import all modules
try:
    from corridor_pruning.drone_model import DroneResult, estimate_drone
    from corridor_pruning.carbon_footprint import calculate_carbon_savings, CarbonResult
    from corridor_pruning.obstacles import load_buildings_gdf, get_max_obstacle_height
    from corridor_pruning.pruning import prune_corridors, ScoredCorridor
    print('✓ All modules import successfully')
except Exception as e:
    print(f'✗ Import error: {e}')
    sys.exit(1)

# Test 2: Verify DroneResult has all fields
try:
    result = estimate_drone(1000)
    assert hasattr(result, 'descend_energy_wh'), 'Missing descend_energy_wh'
    assert hasattr(result, 'climb_cost_usd'), 'Missing climb_cost_usd'
    assert hasattr(result, 'cruise_cost_usd'), 'Missing cruise_cost_usd'
    assert hasattr(result, 'descend_cost_usd'), 'Missing descend_cost_usd'
    print(f'✓ DroneResult has energy decomposition:')
    print(f'    Climb: {result.climb_energy_wh:.1f} Wh (${result.climb_cost_usd:.4f})')
    print(f'    Cruise: {result.cruise_energy_wh:.1f} Wh (${result.cruise_cost_usd:.4f})')
    print(f'    Descend: {result.descend_energy_wh:.1f} Wh (${result.descend_cost_usd:.4f})')
except Exception as e:
    print(f'✗ DroneResult test failed: {e}')
    sys.exit(1)

# Test 3: Verify carbon calculation
try:
    carbon = calculate_carbon_savings(20.5, 1.5, 0.1)
    assert isinstance(carbon, CarbonResult)
    assert carbon.drone_co2_g > 0, 'Drone CO2 should be > 0'
    assert carbon.ground_co2_g > 0, 'Ground CO2 should be > 0'
    assert carbon.co2_saved_g > 0, 'Savings should be > 0'
    assert 0 <= carbon.co2_reduction_pct <= 100, 'Reduction % should be 0-100'
    print(f'✓ Carbon calculation working:')
    print(f'    Drone: {carbon.drone_co2_g:.1f}g, Ground: {carbon.ground_co2_g:.1f}g')
    print(f'    Saved: {carbon.co2_saved_g:.1f}g ({carbon.co2_reduction_pct:.1f}%)')
except Exception as e:
    print(f'✗ Carbon calculation failed: {e}')
    sys.exit(1)

# Test 4: Verify ScoredCorridor has carbon fields
try:
    results = prune_corridors(buildings_csv=None)
    top = results[0]
    assert hasattr(top, 'drone_co2_g'), 'Missing drone_co2_g'
    assert hasattr(top, 'ground_co2_g'), 'Missing ground_co2_g'
    assert hasattr(top, 'co2_saved_g'), 'Missing co2_saved_g'
    assert hasattr(top, 'co2_reduction_pct'), 'Missing co2_reduction_pct'
    print(f'✓ ScoredCorridor carbon metrics:')
    print(f'    Drone CO2: {top.drone_co2_g:.1f}g')
    print(f'    Ground CO2: {top.ground_co2_g:.1f}g')
    print(f'    Saved: {top.co2_saved_g/1000:.3f} kg ({top.co2_reduction_pct:.1f}%)')
except Exception as e:
    print(f'✗ ScoredCorridor test failed: {e}')
    sys.exit(1)

print(f'\n✅ All integration tests passed!')
print(f'   - Energy decomposition: ✓')
print(f'   - Carbon footprint: ✓')
print(f'   - Building obstacles: ✓ (with graceful fallback)')
print(f'   - End-to-end scoring: ✓ ({len(results)} corridors)')
