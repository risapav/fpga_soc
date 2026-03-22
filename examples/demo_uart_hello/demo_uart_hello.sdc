# =============================================================================
# demo_uart_hello.sdc — Timing Constraints
# Target: QMTech EP4CE55F23, 50 MHz
# =============================================================================

# Hlavný systémový clock — 50 MHz (perióda 20 ns)
create_clock -name "SYS_CLK" -period 20.0 [get_ports {SYS_CLK}]

# Automatické odvodenie neistoty hodín (jitter, skew)
derive_clock_uncertainty
