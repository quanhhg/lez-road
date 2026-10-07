[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.202748,105.917191,21.248190,105.965657)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.202748,105.917191,21.248190,105.965657);
  node["barrier"](21.202748,105.917191,21.248190,105.965657);
);
(._; >>;);
out meta;
out count;
