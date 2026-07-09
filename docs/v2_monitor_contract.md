# V2 Monitor Contract

The monitor reads local artifacts only and must surface lifecycle status
separately from generic stale-data warnings.

Campaign fields:

- subscribed market ticker
- event ticker
- market title or name
- market status
- close time or expected expiration
- time to close at launch or time since close
- market evidence validity
- supervisor liveness
- campaign process liveness
- WebSocket message freshness
- market lifecycle status
- exchange heartbeat status

If the subscribed market is finalized, closed, settled, resolved, or expired,
the monitor must show `MARKET_CLOSED_OR_FINALIZED`. Completed bounded canaries
may be quiet without being treated as stale live campaigns. Exchange heartbeat
is `UNKNOWN` unless a recorder explicitly observes it.
