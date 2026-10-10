"""
OMS Project - Redis Lua Scripts for Atomic Risk Reservation
Enforces atomic balance check, portfolio exposure checks, and risk reservation.
"""

# Redis Lua Script for Atomic Risk Reservation
ATOMIC_RISK_RESERVATION_LUA = """
-- KEYS[1]: strategy_balance_key
-- KEYS[2]: strategy_reserved_key
-- KEYS[3]: portfolio_exposure_key
-- ARGV[1]: order_value (qty * price)
-- ARGV[2]: max_gross_exposure

local order_value = tonumber(ARGV[1])
local max_gross_exposure = tonumber(ARGV[2])

local current_balance = tonumber(redis.call('GET', KEYS[1]) or '0')
local current_reserved = tonumber(redis.call('GET', KEYS[2]) or '0')
local current_exposure = tonumber(redis.call('GET', KEYS[3]) or '0')

-- Check 1: Strategy Balance >= Order Value
if current_balance < order_value then
    return {0, 'INSUFFICIENT_STRATEGY_BALANCE', tostring(current_balance)}
end

-- Check 2: Total Portfolio Exposure + Order Value <= Max Gross Exposure
if (current_exposure + order_value) > max_gross_exposure then
    return {0, 'PORTFOLIO_GROSS_EXPOSURE_LIMIT_EXCEEDED', tostring(current_exposure)}
end

-- Atomic Deduct into Reserved State
redis.call('SET', KEYS[1], tostring(current_balance - order_value))
redis.call('SET', KEYS[2], tostring(current_reserved + order_value))
redis.call('SET', KEYS[3], tostring(current_exposure + order_value))

return {1, 'RISK_RESERVED_SUCCESS', tostring(current_balance - order_value)}
"""

# Redis Lua Script for Idempotency Register
IDEMPOTENCY_CHECK_AND_SET_LUA = """
-- KEYS[1]: idempotency_key
-- ARGV[1]: result_json
-- ARGV[2]: ttl_seconds

local existing = redis.call('GET', KEYS[1])
if existing then
    return {1, existing}
end

redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return {0, ARGV[1]}
"""

# Redis Lua Script for Concentration Penalty & Portfolio Correlation Check
CONCENTRATION_PENALTY_RISK_RESERVATION_LUA = """
-- KEYS[1]: strategy_balance_key
-- KEYS[2]: strategy_reserved_key
-- KEYS[3]: portfolio_exposure_key
-- KEYS[4]: symbol_other_pods_position_key
-- ARGV[1]: requested_qty
-- ARGV[2]: order_price
-- ARGV[3]: max_gross_exposure
-- ARGV[4]: concentration_penalty_factor (e.g. 0.5)

local requested_qty = tonumber(ARGV[1])
local price = tonumber(ARGV[2])
local max_gross_exposure = tonumber(ARGV[3])
local penalty_factor = tonumber(ARGV[4] or '0.5')

local other_position = tonumber(redis.call('GET', KEYS[4]) or '0')
local effective_qty = requested_qty

if other_position > 0 then
    effective_qty = requested_qty * penalty_factor
end

local order_value = effective_qty * price
local current_balance = tonumber(redis.call('GET', KEYS[1]) or '0')
local current_reserved = tonumber(redis.call('GET', KEYS[2]) or '0')
local current_exposure = tonumber(redis.call('GET', KEYS[3]) or '0')

if current_balance < order_value then
    return {0, 'INSUFFICIENT_STRATEGY_BALANCE', tostring(current_balance)}
end

if (current_exposure + order_value) > max_gross_exposure then
    return {0, 'PORTFOLIO_GROSS_EXPOSURE_LIMIT_EXCEEDED', tostring(current_exposure)}
end

redis.call('SET', KEYS[1], tostring(current_balance - order_value))
redis.call('SET', KEYS[2], tostring(current_reserved + order_value))
redis.call('SET', KEYS[3], tostring(current_exposure + order_value))

return {1, 'RISK_RESERVED_CONCENTRATION_PENALTY_APPLIED', tostring(effective_qty), tostring(order_value)}
"""

