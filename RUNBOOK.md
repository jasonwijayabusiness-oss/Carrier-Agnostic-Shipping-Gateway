# V3 Runbook: Sendle Shutdown

If SENDLE label creation starts failing (503), the platform:
1) logs failed attempts into `label_attempts`
2) disables SENDLE via `provider_status` (kill switch)
3) opens an incident row in `incidents`
4) re-routes using rate shopping across ALT/AUSPOST

Routing logic:
- Filter by capabilities (pickup/dropoff/printer-free) + max weight + provider enabled
- Among eligible: pick cheapest meeting promised_days
- If none meet promise: pick best available and flag PROMISE_RISK
