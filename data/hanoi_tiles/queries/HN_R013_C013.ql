[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.112672,105.868494,21.158101,105.916915)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.112672,105.868494,21.158101,105.916915);
  node["barrier"](21.112672,105.868494,21.158101,105.916915);
);
(._; >>;);
out meta;
out count;
