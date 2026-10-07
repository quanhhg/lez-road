[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.114318,105.483349,21.159641,105.531658)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.114318,105.483349,21.159641,105.531658);
  node["barrier"](21.114318,105.483349,21.159641,105.531658);
);
(._; >>;);
out meta;
out count;
