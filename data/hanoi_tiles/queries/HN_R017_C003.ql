[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.295296,105.387529,21.340593,105.435869)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.295296,105.387529,21.340593,105.435869);
  node["barrier"](21.295296,105.387529,21.340593,105.435869);
);
(._; >>;);
out meta;
out count;
