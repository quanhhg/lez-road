[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.886809,105.867188,20.932236,105.915534)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.886809,105.867188,20.932236,105.915534);
  node["barrier"](20.886809,105.867188,20.932236,105.915534);
);
(._; >>;);
out meta;
out count;
