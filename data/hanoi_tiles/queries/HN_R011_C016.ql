[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.021489,106.012302,21.066956,106.060734)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.021489,106.012302,21.066956,106.060734);
  node["barrier"](21.021489,106.012302,21.066956,106.060734);
);
(._; >>;);
out meta;
out count;
