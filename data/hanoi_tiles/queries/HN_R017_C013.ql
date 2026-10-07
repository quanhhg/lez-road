[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.293359,105.869551,21.338789,105.918034)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.293359,105.869551,21.338789,105.918034);
  node["barrier"](21.293359,105.869551,21.338789,105.918034);
);
(._; >>;);
out meta;
out count;
