[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.022580,105.819858,21.067995,105.868235)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.022580,105.819858,21.067995,105.868235);
  node["barrier"](21.022580,105.819858,21.067995,105.868235);
);
(._; >>;);
out meta;
out count;
