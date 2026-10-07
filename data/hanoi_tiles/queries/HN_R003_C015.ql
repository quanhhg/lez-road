[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.660405,105.961893,20.705856,106.010190)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.660405,105.961893,20.705856,106.010190);
  node["barrier"](20.660405,105.961893,20.705856,106.010190);
);
(._; >>;);
out meta;
out count;
