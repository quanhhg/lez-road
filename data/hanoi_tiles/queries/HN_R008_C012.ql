[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.887060,105.819120,20.932474,105.867451)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.887060,105.819120,20.932474,105.867451);
  node["barrier"](20.887060,105.819120,20.932474,105.867451);
);
(._; >>;);
out meta;
out count;
