const sliderValue = (position, min, max) => Math.round(min + Math.max(0, Math.min(1, position)) * (max - min));
const GRAVITY = 16;
function predictSliderFlight(anchor, release) {
  const start = {
    // Signed endpoint displacement is release energy, not a legal value.
    x: Math.max(-0.6, Math.min(1.6, release.x)),
    y: Math.max(-0.6, Math.min(0.6, release.y))
  };
  const vy = -18 * start.y;
  const discriminant = vy * vy - 2 * GRAVITY * start.y;
  const duration = Math.max(
    0.12,
    Math.min(
      0.48,
      discriminant >= 0 ? (-vy + Math.sqrt(discriminant)) / GRAVITY : 0.12
    )
  );
  const target = Math.max(
    0,
    Math.min(1, start.x - 18 * (start.x - anchor.x) * duration)
  );
  return {
    start,
    target,
    duration,
    vx: (target - start.x) / duration,
    vy: (-start.y - GRAVITY * duration * duration / 2) / duration
  };
}
function sliderFlightPoint(flight, fraction) {
  const t = Math.max(0, Math.min(1, fraction)) * flight.duration;
  return {
    x: flight.start.x + flight.vx * t,
    y: flight.start.y + flight.vy * t + GRAVITY * t * t / 2
  };
}
export {
  predictSliderFlight,
  sliderFlightPoint,
  sliderValue
};
