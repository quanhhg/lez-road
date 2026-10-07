[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.248684,105.772915,21.294088,105.821355)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.248684,105.772915,21.294088,105.821355);
  node["barrier"](21.248684,105.772915,21.294088,105.821355);
);
(._; >>;);
out meta;
out count;
