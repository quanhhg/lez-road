[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.706819,105.722120,20.752206,105.770364)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.706819,105.722120,20.752206,105.770364);
  node["barrier"](20.706819,105.722120,20.752206,105.770364);
);
(._; >>;);
out meta;
out count;
