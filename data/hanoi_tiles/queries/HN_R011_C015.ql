[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.021782,105.964192,21.067237,106.012610)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.021782,105.964192,21.067237,106.012610);
  node["barrier"](21.021782,105.964192,21.067237,106.012610);
);
(._; >>;);
out meta;
out count;
