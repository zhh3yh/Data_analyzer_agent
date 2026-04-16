"""Quick test: verify PlotStr wrapper initializes and can call MATLAB."""

import sys

sys.path.insert(0, "D:/Data_analyzer_agent")

from src.tools.plotstr_wrapper import PlotStrWrapper, PlotStrConfig

cfg = PlotStrConfig(
    plotstr_root="C:/plotstr",
    matlab_executable="C:/Program Files/MATLAB/R2022b/bin/matlab.exe",
    output_dir="D:/Data_analyzer_agent/src/data/plotstr_outputs",
)
w = PlotStrWrapper(cfg)
print("Wrapper initialized OK")
print(f"  root: {w._root}")
print(f"  ps.m exists: {(w._root / 'ps.m').is_file()}")

# Test: list ports in our MAT file using the wrapper
mat_file = r"D:\data\RVMTIVXR-32293_CustomerSpec_analysis\NCAP_test\5K45_MG20_20251027_053149_001___AEB___R302C1__5K3p0p2D1.mf4_distilled.mat"
print(f"\nListing ports in: {mat_file.split(chr(92))[-1]}")
ports = w.list_ports(mat_file)
print(f"  Found {len(ports)} ports")
for p in ports[:10]:
    print(f"    - {p}")
if len(ports) > 10:
    print(f"    ... and {len(ports) - 10} more")

# Test: read a signal via wrapper
print(
    f"\nReading signal via wrapper: TimbaRunnable_m_targetGatewayObjects.m_objectDataList.m_dx.m_value"
)
sig = w.read_signal(
    mat_file, "TimbaRunnable_m_targetGatewayObjects.m_objectDataList.m_dx.m_value"
)
print(f"  Values shape: {sig['values'].shape}")
print(f"  Range: {sig['values'].min():.2f} ~ {sig['values'].max():.2f}")

# Test: get time span
tmin, tmax = w.get_time_span(mat_file)
print(f"\nTime span: {tmin:.0f}ms ~ {tmax:.0f}ms ({(tmax-tmin)/1000:.2f}s)")

print("\n✓ All PlotStr wrapper tests passed!")
