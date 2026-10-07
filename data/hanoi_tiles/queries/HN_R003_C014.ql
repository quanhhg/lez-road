[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.660679,105.913897,20.706117,105.962180)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.660679,105.913897,20.706117,105.962180);
  node["barrier"](20.660679,105.913897,20.706117,105.962180);
);
(._; >>;);
out meta;
out count;
