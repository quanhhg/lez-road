[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.842345,105.722764,20.887733,105.771053)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.842345,105.722764,20.887733,105.771053);
  node["barrier"](20.842345,105.722764,20.887733,105.771053);
);
(._; >>;);
out meta;
out count;
