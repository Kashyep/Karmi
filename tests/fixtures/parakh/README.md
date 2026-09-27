# Parakh interop fixtures

`policy-2026.09.27.1/` is an unmodified PolicyBundleV1 exported by Parakh (commit 41674dd,
clean tree) from its synthetic flywheel: 4,000 simulated runs -> reward -> LinUCB -> OPE ->
simulated 60-case regression -> verifier with owner ceilings -> operator approval -> signed export.
Its actions are Parakh's simulated models (`sim/cheap`, `sim/balanced`, `sim/flagship`), so
Karmi's own registry must reject it; tests pass the sim actions explicitly to prove format
compatibility. Public key: `8588d3d16dfd2a08e691a8da48aea9925f4dea853ba036477593dcdcebbe21d5`.
The throwaway signing key was discarded and never committed.
