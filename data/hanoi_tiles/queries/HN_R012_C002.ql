[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.069532,105.338809,21.114815,105.387061)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.069532,105.338809,21.114815,105.387061);
  node["barrier"](21.069532,105.338809,21.114815,105.387061);
);
(._; >>;);
out meta;
out count;
