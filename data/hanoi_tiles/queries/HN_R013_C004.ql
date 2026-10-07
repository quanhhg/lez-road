[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.114462,105.435203,21.159772,105.483498)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.114462,105.435203,21.159772,105.483498);
  node["barrier"](21.114462,105.435203,21.159772,105.483498);
);
(._; >>;);
out meta;
out count;
