use std::{
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};

use crate::config::GatewayConfig;

#[derive(Clone)]
pub struct RateLimiter {
    enabled: bool,
    rps: u32,
    burst_size: u32,
    bucket: Arc<Mutex<TokenBucket>>,
}

#[derive(Debug)]
struct TokenBucket {
    tokens: f64,
    last_refill: Instant,
}

impl RateLimiter {
    pub fn from_config(config: &GatewayConfig) -> Self {
        Self::new(
            config.ratelimit_rps,
            config.ratelimit_burst_size,
            config.ratelimit_enabled,
        )
    }

    pub fn new(rps: u32, burst_size: u32, enabled: bool) -> Self {
        let rps = rps.max(1);
        let burst_size = burst_size.max(1);
        Self {
            enabled,
            rps,
            burst_size,
            bucket: Arc::new(Mutex::new(TokenBucket {
                tokens: burst_size as f64,
                last_refill: Instant::now(),
            })),
        }
    }

    pub async fn acquire(&self) {
        if !self.enabled {
            return;
        }

        loop {
            let wait = self.try_take();
            if wait.is_zero() {
                return;
            }
            tokio::time::sleep(wait).await;
        }
    }

    pub fn enabled(&self) -> bool {
        self.enabled
    }

    pub fn rps(&self) -> u32 {
        self.rps
    }

    pub fn burst_size(&self) -> u32 {
        self.burst_size
    }

    fn try_take(&self) -> Duration {
        let now = Instant::now();
        let mut bucket = self.bucket.lock().expect("rate limiter lock poisoned");
        let elapsed = now.duration_since(bucket.last_refill).as_secs_f64();
        bucket.tokens = (bucket.tokens + elapsed * self.rps as f64).min(self.burst_size as f64);
        bucket.last_refill = now;

        if bucket.tokens >= 1.0 {
            bucket.tokens -= 1.0;
            return Duration::ZERO;
        }

        let needed = 1.0 - bucket.tokens;
        Duration::from_secs_f64(needed / self.rps as f64)
    }
}

#[cfg(test)]
mod tests {
    use super::RateLimiter;
    use crate::config::GatewayConfig;
    use std::time::{Duration, Instant};

    #[test]
    fn loads_rate_limiter_from_gateway_config() {
        let config = GatewayConfig::from_lookup(|key| match key {
            "GATEWAY_RATELIMIT_ENABLED" => Some("true".to_string()),
            "GATEWAY_RATELIMIT_RPS" => Some("25".to_string()),
            "GATEWAY_RATELIMIT_BURST_SIZE" => Some("3".to_string()),
            _ => None,
        });

        let limiter = RateLimiter::from_config(&config);

        assert!(limiter.enabled());
        assert_eq!(limiter.rps(), 25);
        assert_eq!(limiter.burst_size(), 3);
    }

    #[tokio::test]
    async fn disabled_limiter_does_not_wait() {
        let limiter = RateLimiter::new(1, 1, false);
        let start = Instant::now();

        for _ in 0..5 {
            limiter.acquire().await;
        }

        assert!(start.elapsed() < Duration::from_millis(20));
    }

    #[tokio::test]
    async fn enabled_limiter_waits_after_burst_is_spent() {
        let limiter = RateLimiter::new(50, 1, true);
        limiter.acquire().await;

        let start = Instant::now();
        limiter.acquire().await;

        assert!(start.elapsed() >= Duration::from_millis(10));
    }
}
