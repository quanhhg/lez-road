[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.023453,105.627403,21.068816,105.675724)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.023453,105.627403,21.068816,105.675724);
  node["barrier"](21.023453,105.627403,21.068816,105.675724);
);
(._; >>;);
out meta;
out count;
