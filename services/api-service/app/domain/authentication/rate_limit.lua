-- Auth OTP challenge rolling rate limit (phone + IP dual ZSET).
-- Atomic: Redis TIME clock, prune window, check both dimensions, ZADD winner member.
--
-- KEYS[1] = phone ZSET key  (tm:{env}:auth:v1:otp:rl:phone:{hmac_hex})
-- KEYS[2] = ip ZSET key     (tm:{env}:auth:v1:otp:rl:ip:{hmac_hex})
-- ARGV[1] = member id (unique per idempotency winner, e.g. UUID)
-- ARGV[2] = phone_limit (default 5)
-- ARGV[3] = ip_limit (default 20)
-- ARGV[4] = window_ms (default 3600000)
-- ARGV[5] = ttl_seconds (slightly > window, default 3700)
--
-- Returns array:
--   { allowed (1|0), dimension (""|"phone"|"ip"), retry_after_seconds,
--     phone_count, ip_count }

local phone_key = KEYS[1]
local ip_key = KEYS[2]
local member = ARGV[1]
local phone_limit = tonumber(ARGV[2])
local ip_limit = tonumber(ARGV[3])
local window_ms = tonumber(ARGV[4])
local ttl_seconds = tonumber(ARGV[5])

local t = redis.call('TIME')
local now_ms = (tonumber(t[1]) * 1000) + math.floor(tonumber(t[2]) / 1000)
local cutoff = now_ms - window_ms

redis.call('ZREMRANGEBYSCORE', phone_key, '-inf', cutoff)
redis.call('ZREMRANGEBYSCORE', ip_key, '-inf', cutoff)

local phone_count = redis.call('ZCARD', phone_key)
local ip_count = redis.call('ZCARD', ip_key)

local function retry_after_for(key)
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  if oldest == nil or #oldest < 2 then
    return 1
  end
  local oldest_score = tonumber(oldest[2])
  local remain_ms = (oldest_score + window_ms) - now_ms
  if remain_ms <= 0 then
    return 1
  end
  local secs = math.ceil(remain_ms / 1000)
  if secs < 1 then
    return 1
  end
  return secs
end

if phone_count >= phone_limit then
  return {0, 'phone', retry_after_for(phone_key), phone_count, ip_count}
end

if ip_count >= ip_limit then
  return {0, 'ip', retry_after_for(ip_key), phone_count, ip_count}
end

redis.call('ZADD', phone_key, now_ms, member)
redis.call('ZADD', ip_key, now_ms, member)
redis.call('EXPIRE', phone_key, ttl_seconds)
redis.call('EXPIRE', ip_key, ttl_seconds)

return {1, '', 0, phone_count + 1, ip_count + 1}
