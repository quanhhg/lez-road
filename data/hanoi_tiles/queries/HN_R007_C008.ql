[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.842751,105.626651,20.888113,105.674912)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.842751,105.626651,20.888113,105.674912);
  node["barrier"](20.842751,105.626651,20.888113,105.674912);
);
(._; >>;);
out meta;
out count;
