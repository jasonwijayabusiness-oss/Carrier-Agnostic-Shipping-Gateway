-- Failed Sendle label attempts (impact)
SELECT order_id, created_at, error_code, error_message
FROM label_attempts
WHERE provider='SENDLE' AND success=0
ORDER BY created_at DESC
LIMIT 50;

-- Carrier config
SELECT * FROM carriers ORDER BY provider;

-- Promise-risk shipments
SELECT order_id, provider, estimated_cost, estimated_days, selection_reason, created_at
FROM shipments
WHERE selection_reason LIKE '%PROMISE_RISK%'
ORDER BY created_at DESC;

-- Eligibility for a specific order
SELECT order_id, provider, eligible, ineligible_reason, quoted_cost, estimated_days, lane_type, created_at
FROM rate_quotes
WHERE order_id='ORDER-0001'
ORDER BY created_at DESC;
