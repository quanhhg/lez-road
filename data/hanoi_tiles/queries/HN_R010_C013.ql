[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.977155,105.867709,21.022583,105.916084)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.977155,105.867709,21.022583,105.916084);
  node["barrier"](20.977155,105.867709,21.022583,105.916084);
);
(._; >>;);
out meta;
out count;
