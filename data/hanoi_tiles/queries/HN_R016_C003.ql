[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.250121,105.387411,21.295417,105.435736)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.250121,105.387411,21.295417,105.435736);
  node["barrier"](21.250121,105.387411,21.295417,105.435736);
);
(._; >>;);
out meta;
out count;
