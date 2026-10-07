[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.797757,105.578421,20.843105,105.626654)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.797757,105.578421,20.843105,105.626654);
  node["barrier"](20.797757,105.578421,20.843105,105.626654);
);
(._; >>;);
out meta;
out count;
