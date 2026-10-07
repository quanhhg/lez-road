[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.024355,105.338707,21.069638,105.386944)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.024355,105.338707,21.069638,105.386944);
  node["barrier"](21.024355,105.338707,21.069638,105.386944);
);
(._; >>;);
out meta;
out count;
