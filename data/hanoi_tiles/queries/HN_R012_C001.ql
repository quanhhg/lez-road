[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.069635,105.290677,21.114905,105.338915)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.069635,105.290677,21.114905,105.338915);
  node["barrier"](21.069635,105.290677,21.114905,105.338915);
);
(._; >>;);
out meta;
out count;
