[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.931982,105.867448,20.977410,105.915809)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.931982,105.867448,20.977410,105.915809);
  node["barrier"](20.931982,105.867448,20.977410,105.915809);
);
(._; >>;);
out meta;
out count;
