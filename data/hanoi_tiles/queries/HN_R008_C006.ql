[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.888279,105.530694,20.933615,105.578943)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.888279,105.530694,20.933615,105.578943);
  node["barrier"](20.888279,105.530694,20.933615,105.578943);
);
(._; >>;);
out meta;
out count;
