[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.933755,105.434679,20.979065,105.482914)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.933755,105.434679,20.979065,105.482914);
  node["barrier"](20.933755,105.434679,20.979065,105.482914);
);
(._; >>;);
out meta;
out count;
