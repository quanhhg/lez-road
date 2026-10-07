[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.112926,105.820353,21.158342,105.868760)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.112926,105.820353,21.158342,105.868760);
  node["barrier"](21.112926,105.820353,21.158342,105.868760);
);
(._; >>;);
out meta;
out count;
