[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.706114,105.866156,20.751540,105.914441)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.706114,105.866156,20.751540,105.914441);
  node["barrier"](20.706114,105.866156,20.751540,105.914441);
);
(._; >>;);
out meta;
out count;
