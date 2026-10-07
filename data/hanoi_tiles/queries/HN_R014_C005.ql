[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.159493,105.483495,21.204817,105.531819)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.159493,105.483495,21.204817,105.531819);
  node["barrier"](21.159493,105.483495,21.204817,105.531819);
);
(._; >>;);
out meta;
out count;
