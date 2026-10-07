[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.069416,105.386941,21.114712,105.435206)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.069416,105.386941,21.114712,105.435206);
  node["barrier"](21.069416,105.386941,21.114712,105.435206);
);
(._; >>;);
out meta;
out count;
