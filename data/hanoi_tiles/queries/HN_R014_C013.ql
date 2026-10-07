[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.157844,105.868757,21.203274,105.917194)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.157844,105.868757,21.203274,105.917194);
  node["barrier"](21.157844,105.868757,21.203274,105.917194);
);
(._; >>;);
out meta;
out count;
