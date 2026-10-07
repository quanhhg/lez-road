[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.797925,105.530378,20.843261,105.578597)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.797925,105.530378,20.843261,105.578597);
  node["barrier"](20.797925,105.530378,20.843261,105.578597);
);
(._; >>;);
out meta;
out count;
