[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.023965,105.483057,21.069288,105.531336)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.023965,105.483057,21.069288,105.531336);
  node["barrier"](21.023965,105.483057,21.069288,105.531336);
);
(._; >>;);
out meta;
out count;
