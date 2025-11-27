-- Sample SQL queries to inspect generated fraud graph data

-- Row counts across tables
SELECT 'accounts' AS table_name, COUNT(*) FROM graph_accounts
UNION ALL SELECT 'devices', COUNT(*) FROM graph_devices
UNION ALL SELECT 'account_device', COUNT(*) FROM graph_account_device
UNION ALL SELECT 'transactions', COUNT(*) FROM graph_transactions;

-- Random accounts to spot fraud flags
SELECT id, account_number, customer_name, risk_score, is_fraud
FROM graph_accounts
ORDER BY random()
LIMIT 10;

-- Flagged vs legit transactions (sample)
SELECT tx_ref, from_account_id, to_account_id, amount, channel, timestamp, is_flagged, tags
FROM graph_transactions
ORDER BY is_flagged DESC, random()
LIMIT 20;

-- Mule ring: accounts sharing mule devices
SELECT d.device_id,
       COUNT(DISTINCT ad.account_id) AS accounts_on_device
FROM graph_devices d
JOIN graph_account_device ad ON ad.device_id = d.id
WHERE d.device_id LIKE 'MULE-DEV%'
GROUP BY d.device_id
ORDER BY accounts_on_device DESC;

-- Mule ring transactions
SELECT tx_ref, from_account_id, to_account_id, amount, timestamp, tags
FROM graph_transactions
WHERE tags IN ('mule_ring', 'mule_layer')
ORDER BY timestamp DESC
LIMIT 50;

-- Identity overlap: devices shared by many accounts
SELECT d.device_id,
       COUNT(DISTINCT ad.account_id) AS accounts_sharing
FROM graph_devices d
JOIN graph_account_device ad ON ad.device_id = d.id
GROUP BY d.device_id
HAVING COUNT(DISTINCT ad.account_id) > 2
ORDER BY accounts_sharing DESC;

-- Identity overlap transactions
SELECT tx_ref, from_account_id, to_account_id, amount, timestamp, tags
FROM graph_transactions
WHERE tags = 'identity_overlap'
ORDER BY timestamp DESC
LIMIT 50;

-- Top devices by number of linked accounts
SELECT d.device_id,
       COUNT(DISTINCT ad.account_id) AS accounts_on_device
FROM graph_devices d
JOIN graph_account_device ad ON ad.device_id = d.id
GROUP BY d.device_id
ORDER BY accounts_on_device DESC
LIMIT 10;

-- Daily transaction counts by tag
SELECT date_trunc('day', timestamp) AS day, tags, COUNT(*) AS tx_count
FROM graph_transactions
GROUP BY day, tags
ORDER BY day DESC, tx_count DESC;
