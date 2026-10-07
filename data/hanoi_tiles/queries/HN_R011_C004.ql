[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.024109,105.434940,21.069419,105.483205)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.024109,105.434940,21.069419,105.483205);
  node["barrier"](21.024109,105.434940,21.069419,105.483205);
);
(._; >>;);
out meta;
out count;
