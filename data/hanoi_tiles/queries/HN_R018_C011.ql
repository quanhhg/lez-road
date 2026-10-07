[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.339029,105.773388,21.384433,105.821858)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.339029,105.773388,21.384433,105.821858);
  node["barrier"](21.339029,105.773388,21.384433,105.821858);
);
(._; >>;);
out meta;
out count;
