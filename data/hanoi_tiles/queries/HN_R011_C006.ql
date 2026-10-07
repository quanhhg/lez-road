[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.023808,105.531173,21.069145,105.579466)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.023808,105.531173,21.069145,105.579466);
  node["barrier"](21.023808,105.531173,21.069145,105.579466);
);
(._; >>;);
out meta;
out count;
