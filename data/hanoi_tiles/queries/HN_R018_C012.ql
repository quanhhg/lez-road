[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.338786,105.821603,21.384204,105.870087)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.338786,105.821603,21.384204,105.870087);
  node["barrier"](21.338786,105.821603,21.384204,105.870087);
);
(._; >>;);
out meta;
out count;
