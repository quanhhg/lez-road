[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.023255,105.675518,21.068631,105.723853)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.023255,105.675518,21.068631,105.723853);
  node["barrier"](21.023255,105.675518,21.068631,105.723853);
);
(._; >>;);
out meta;
out count;
