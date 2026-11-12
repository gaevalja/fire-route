/*
 * Fire evacuation scenario maker: all adjustable simulation numbers live here.
 * Values are illustrative model parameters, not measured fire-safety data.
 */
(function (global) {
  "use strict";

  const CONFIG = Object.freeze({
    FLOORS: 10,
    ROOF_FLOOR: 11,
    ROOMS_ON_FIRST_FLOOR: 4,
    ROOMS_ON_UPPER_FLOOR: 9,
    CORRIDOR_SEGMENTS: 5,
    WIND_OPTIONS: Object.freeze([1, 5, 10, 15]),
    DEFAULT_WIND: 5,
    TIME_STEP_SECONDS: 1,
    SECONDS_PER_MINUTE: 60,

    // A size is a relative volume unit. Lobby and roof are editable defaults.
    ZONE_SIZE: Object.freeze({
      room: 1,
      corridor: 1,
      stair: 2,
      elevator: 1,
      lobby: 5,
      roof: 5
    }),

    INITIAL_FIRE: 18,
    MAX_LEVEL: 100,
    SMOKE_ABOVE_FIRE_CAP: 30,
    FIRE_GROWTH_PER_MINUTE: 6.5,
    FIRE_SPREAD_PER_MINUTE: 0.16,
    SMOKE_GENERATION_PER_FIRE: 0.8,
    SMOKE_SPREAD_PER_MINUTE: 0.8,
    SMOKE_DIRECT_FIRE_TRANSFER: 0.7,
    WIND_MULTIPLIER: Object.freeze({ 1: 0.75, 5: 1, 10: 1.3, 15: 1.6 }),

    // Per-minute probability rises quadratically after this fire level.
    // The total cap keeps scenario maps readable while preserving randomness.
    COLLAPSE_FIRE_THRESHOLD: 55,
    COLLAPSE_MAX_PROBABILITY: 0.001,
    MAX_COLLAPSED_ZONES: 2,

    // Event history is bounded so long-running scenarios remain responsive.
    EVENT_HISTORY_LIMIT: 300
  });

  global.FireEvacConfig = CONFIG;
})(typeof window !== "undefined" ? window : globalThis);
