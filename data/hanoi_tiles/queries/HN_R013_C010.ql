[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.113392,105.724069,21.158782,105.772448)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.113392,105.724069,21.158782,105.772448);
  node["barrier"](21.113392,105.724069,21.158782,105.772448);
);
(._; >>;);
out meta;
out count;
